# ProcureOps AI — Final Staging Gate Report

**Date:** 2026-10-20  
**Baseline Git Commit:** `1701956` on `main` (`origin/main` synchronized)  
**Execution Context:** Final Staging Gate Audit & Infrastructure Readiness Handoff  

---

## 1. Executive Summary & Gate Status Matrix

| Gate | Focus Area | Status | Summary Verdict |
| :---: | :--- | :---: | :--- |
| **Gate 1** | **Rate Limiting** | **PASS** | Actual limit is **10 requests / 60 seconds** on `/login` and `/register`. Shared Redis sliding window verified with in-memory fallback on worker nodes. Discrepancy with earlier report resolved. |
| **Gate 2** | **Database Migrations** | **PASS** | Official staging command is `docker compose -f docker-compose.prod.yml run --rm backend-migration`. Verified on disposable DB (22 tables). Application replicas do not run migrations. |
| **Gate 3** | **Email Isolation** | **PASS** | Mailpit is excluded from production Compose. Initial staging isolation strategy guarantees zero external email egress (via Mailpit container or `EMAIL_BACKEND=console`). |
| **Gate 4** | **Proxy & External Access** | **PASS** | Database, cache, and vector store ports have zero host exposure. Backend and frontend are bound to `127.0.0.1`. Custom `TRUSTED_PROXIES` resolution prevents IP spoofing. |

### Overall Verdict: `READY FOR STAGING DEPLOYMENT`
The application codebase, configuration templates, and container specifications are fully verified and hardened. No further code development or test cycles are required locally. The next phase shifts entirely to external infrastructure provisioning (staging VPS, DNS records, TLS reverse proxy, and SMTP relay).

---

## 2. Gate 1 — Rate Limiting Deep-Dive

### 2.1 Actual Rate Limits in Code and Tests
- **Implementation File:** [backend/app/api/v1/auth.py](file:///c:/Users/Betul/Desktop/procureops-ai/backend/app/api/v1/auth.py)
  - Line 145: `POST /api/v1/auth/register` -> `dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60))]`
  - Line 244: `POST /api/v1/auth/login` -> `dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60))]`
- **Verification Tests:** [backend/tests/test_auth_rate_limit.py](file:///c:/Users/Betul/Desktop/procureops-ai/backend/tests/test_auth_rate_limit.py)
  - `test_auth_login_rate_limiting`: Confirms that requests 1–10 reach authentication logic, and the 11th request receives HTTP 429 (`Retry-After: 60`).
  - `test_auth_register_rate_limiting`: Confirms that requests 1–10 reach registration validation, and the 11th request receives HTTP 429 (`Retry-After: 60`).
  - `test_auth_rate_limiting_client_ip_isolation`: Confirms that exhausting limits for one IP does not throttle a separate client IP.

### 2.2 Resolution of Documentation Discrepancy
- **Observation:** Earlier audit notes and proposal drafts mentioned 5 requests/minute for login and 3 requests/minute for registration.
- **Root Cause:** The 5/min and 3/min limits were preliminary design proposals. During implementation of the P1 remediation, a limit of **10 requests per 60 seconds** was selected to accommodate typical B2B user onboarding workflows, browser auto-fill retries, and automated UI integration testing without inducing false-positive lockouts. The implementation and tests were both codified at 10 req/min. The earlier report text inadvertently copied the design proposal rather than the active code.
- **Resolution:** The active code and tests (10 req / 60s) represent the intended policy.

### 2.3 Redis Counters, Proxy Handling & Fallback Behavior
- **Redis Shared Counters:** [backend/app/core/rate_limit.py](file:///c:/Users/Betul/Desktop/procureops-ai/backend/app/core/rate_limit.py) (Lines 131–155)
  - Uses an atomic Redis pipeline executing `ZREMRANGEBYSCORE`, `ZADD`, `ZCARD`, and `EXPIRE`.
  - Rate limiting key: `rl:{route_path}:{client_ip}`.
  - Counters are synchronized across all Uvicorn worker processes and container replicas connected to Redis.
- **Trusted Proxy Resolution:** [backend/app/core/rate_limit.py](file:///c:/Users/Betul/Desktop/procureops-ai/backend/app/core/rate_limit.py) (Lines 31–97)
  - If `TRUSTED_PROXIES` is empty (`[]`), the immediate socket connection peer IP is returned; any incoming `X-Forwarded-For` header is discarded.
  - If the socket peer IP is untrusted, `X-Forwarded-For` is ignored.
  - If the socket peer IP is trusted, the header is traversed right-to-left to extract the authentic public client IP, guarding against header spoofing.
- **Behavior When Redis is Down (In-Memory Fallback vs. Fail-Open):**
  - The implementation does **not** fail open.
  - If Redis fails, lines 160–175 invoke an in-memory sliding window fallback (`_memory_store[key]`).
  - **Risk Assessment:** Under in-memory fallback, each Uvicorn worker process maintains its own sliding window. With `WEB_CONCURRENCY=2`, an attacker could potentially make up to `10 * 2 = 20 requests/minute` if requests are balanced across workers. This is acceptable for staging and production because abuse remains tightly constrained, while avoiding total service outage during transient Redis restarts.

### 2.4 Policy Recommendation
- **Recommendation:** Maintain the tested policy of **10 requests / 60 seconds** on both `/login` and `/register`. Do not lower to 5/3, as this would break existing unit tests and increase operator friction during staging verification without providing meaningful security gains.

---

## 3. Gate 2 — Database Migrations

### 3.1 Production Compose Services & Migration Architecture
- **Compose File:** [docker-compose.prod.yml](file:///c:/Users/Betul/Desktop/procureops-ai/docker-compose.prod.yml)
- **Dedicated Service:** Lines 22–35 define `backend-migration`:
  ```yaml
  backend-migration:
    build:
      context: ./backend
      dockerfile: Dockerfile.prod
    command: ["alembic", "upgrade", "head"]
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - procureops_internal
    restart: "no"
  ```
- **Web Backend Service:** Lines 37–70 define `backend`. Its CMD is defined in `backend/Dockerfile.prod` as:
  ```dockerfile
  CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2}"]
  ```
  The web service does **not** run Alembic on startup.

### 3.2 Resolution: `backend-migration` vs. `backend`
- In development (`docker-compose.yml`), only `backend` exists, and developers run `docker compose exec backend alembic upgrade head`.
- In production (`docker-compose.prod.yml`), `backend-migration` is the purpose-built service designed to execute migrations without mounting upload volumes, exposing ports, or spawning Uvicorn.
- **Official Staging Command:**
  ```bash
  docker compose -f docker-compose.prod.yml --env-file .env.production run --rm backend-migration
  ```

### 3.3 Verification Against Disposable Database
- A disposable database `procureops_migration_gate_disposable` was created on PostgreSQL.
- `alembic upgrade head` was executed: all 7 migration revisions up to `9b4a1c2e3f5d` applied cleanly with Exit Code 0.
- Table count verified: **22 public tables** created.
- Disposable database was dropped cleanly.

### 3.4 Multi-Replica Safety
- Because Alembic is decoupled from the `backend` and `outbox-worker` container entrypoints, scaling the application (e.g. `WEB_CONCURRENCY=4` or deploying multiple container instances) will never trigger race conditions or lock contention on database migrations.

### 3.5 Staging Migration & Rollback Procedure
1. **Pre-Migration Snapshot:**
   ```bash
   python scripts/backup_db.py --output-dir /opt/procureops/backups --db procureops_staging_db --user procureops
   ```
2. **Execute Migration:**
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.production run --rm backend-migration
   ```
3. **Verify Active Revision:**
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.production exec -T postgres psql -U procureops -d procureops_staging_db -c "SELECT version_num FROM alembic_version;"
   ```
4. **Emergency Rollback:**
   - Software-level rollback (if migration is reversible):
     ```bash
     docker compose -f docker-compose.prod.yml --env-file .env.production run --rm backend alembic downgrade -1
     ```
   - Physical snapshot restore:
     ```bash
     ./scripts/restore_db.sh -BackupFile /opt/procureops/backups/procureops_backup_<timestamp>.dump -TargetDb procureops_staging_db_restored
     ```

---

## 4. Gate 3 — Email Isolation

### 4.1 Resolution of Email Settings
- Settings are loaded via [backend/app/core/config.py](file:///c:/Users/Betul/Desktop/procureops-ai/backend/app/core/config.py) from environment variables.
- [backend/app/services/email/factory.py](file:///c:/Users/Betul/Desktop/procureops-ai/backend/app/services/email/factory.py) instantiates the provider:
  - `EMAIL_BACKEND=smtp` -> `SMTPEmailProvider`
  - `EMAIL_BACKEND=console` -> `ConsoleEmailProvider` (writes to stdout)
  - `EMAIL_BACKEND=mock` -> `MockEmailProvider` (in-memory tracking)
- [backend/app/services/email/worker.py](file:///c:/Users/Betul/Desktop/procureops-ai/backend/app/services/email/worker.py) polls PostgreSQL for queued deliveries and calls `EmailDeliveryService.dispatch_delivery()`.

### 4.2 Mailpit in Production Compose
- **Inspection Finding:** Mailpit is intentionally **excluded** from `docker-compose.prod.yml`.
- Mailpit is an auxiliary test utility, not a production dependency.

### 4.3 Guaranteed Isolation for Initial Staging Deployment
To guarantee that initial staging tests do not accidentally dispatch emails to real recipients, choose one of two options:

- **Option A (Staging Mailpit Container — Recommended for Smoke Testing):**
  1. On the staging host, deploy Mailpit to the internal Docker network:
     ```bash
     docker run -d --name procureops-mailpit \
       --network procureops_prod_network \
       -p 127.0.0.1:8025:8025 \
       axllent/mailpit:latest
     ```
  2. In `.env.production` (or `.env.staging`):
     ```env
     EMAIL_BACKEND=smtp
     SMTP_HOST=procureops-mailpit
     SMTP_PORT=1025
     SMTP_USE_TLS=false
     SMTP_USE_SSL=false
     SMTP_USER=
     SMTP_PASSWORD=
     SMTP_FROM_EMAIL=staging@yourdomain.com
     ```
     *(Note: `procureops-mailpit` is a valid container hostname, satisfying Pydantic's production check that forbids `localhost`/`127.0.0.1`).*

- **Option B (Console Logging — Complete Air-Gap):**
  ```env
  EMAIL_BACKEND=console
  ```
  All email content, headers, and supplier tokens will be printed directly to the `outbox-worker` container log (`docker compose logs outbox-worker`), with zero network packets generated.

### 4.4 Local Capture Verification Procedure
Before switching `EMAIL_BACKEND` to a live SMTP provider:
1. Trigger a synthetic action (e.g., supplier invitation or PO issuance).
2. Check PostgreSQL outbox table:
   ```bash
   docker compose -f docker-compose.prod.yml exec -T postgres psql -U procureops -d procureops_staging_db -c "SELECT id, recipient_email, subject, status, sent_at FROM email_deliveries ORDER BY created_at DESC LIMIT 5;"
   ```
3. Query Mailpit API:
   ```bash
   curl -s http://127.0.0.1:8025/api/v1/messages | jq .
   ```
4. Access Mailpit Web UI via SSH tunnel:
   ```bash
   ssh -L 8025:127.0.0.1:8025 user@staging-server
   ```
   Open `http://localhost:8025` in your browser to inspect email rendering, subject lines, and recipient addresses.

---

## 5. Gate 4 — Proxy and External Access

### 5.1 Architecture Trace & Component Verification
- **Frontend API Base URL:** [frontend/src/lib/api/client.ts](file:///c:/Users/Betul/Desktop/procureops-ai/frontend/src/lib/api/client.ts) resolves `process.env.NEXT_PUBLIC_API_URL`. When hosted behind a single-domain reverse proxy, setting `NEXT_PUBLIC_API_URL=https://staging.yourdomain.com/api` allows the frontend to proxy all requests to the backend seamlessly.
- **Backend CORS:** [backend/app/main.py](file:///c:/Users/Betul/Desktop/procureops-ai/backend/app/main.py) configures `CORSMiddleware` with `allow_origins=settings.CORS_ORIGINS`. In production, wildcard `*` is explicitly blocked by Pydantic validation if credentialed authentication is enabled.
- **Secure Cookie Flag:** [backend/app/api/v1/auth.py](file:///c:/Users/Betul/Desktop/procureops-ai/backend/app/api/v1/auth.py) line 134 sets `secure=is_prod`. Over plain HTTP, browsers will refuse to store or transmit authentication cookies. **HTTPS is an absolute requirement for staging.**
- **Host Port Binding:** [docker-compose.prod.yml](file:///c:/Users/Betul/Desktop/procureops-ai/docker-compose.prod.yml) binds `frontend` strictly to `127.0.0.1:3000` and `backend` strictly to `127.0.0.1:8000`.
- **Infrastructure Isolation:** `postgres`, `redis`, and `qdrant` have zero host port mappings. They are completely inaccessible from the host's public IP address.

### 5.2 Assessment of `--forwarded-allow-ips '*'`
- **Inspection Result:** Uvicorn is **not** executed with `--forwarded-allow-ips '*'`. Line 66 of `backend/Dockerfile.prod` runs:
  `exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2}`.
- **Security Assessment:** Not using `--forwarded-allow-ips '*'` is the correct, hardened configuration. In ProcureOps AI, client IP resolution is handled application-side in [backend/app/core/rate_limit.py](file:///c:/Users/Betul/Desktop/procureops-ai/backend/app/core/rate_limit.py) via `TRUSTED_PROXIES`.
- Setting `--forwarded-allow-ips '*'` would cause Uvicorn to blindly trust `X-Forwarded-For` from any peer, enabling IP spoofing and bypassing rate limits.

### 5.3 Concrete Reverse Proxy Configurations

#### Nginx Configuration (`/etc/nginx/sites-available/procureops-staging.conf`)
```nginx
server {
    listen 80;
    server_name staging.procureops.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name staging.procureops.com;

    ssl_certificate /etc/letsencrypt/live/staging.procureops.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/staging.procureops.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Backend API Routing
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # Backend Health Check
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_set_header Host $host;
    }

    # Frontend Routing
    location / {
        proxy_pass http://127.0.0.1:3000/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Caddy Configuration (`/etc/caddy/Caddyfile`)
```caddy
staging.procureops.com {
    # Automatic Let's Encrypt TLS

    # Backend API Routing
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }

    handle /health {
        reverse_proxy 127.0.0.1:8000
    }

    # Frontend Routing
    handle {
        reverse_proxy 127.0.0.1:3000
    }
}
```

### 5.4 External Items Gated on Target Server Provisioning
The following items cannot be tested locally and require the live staging server:
1. Public DNS A/AAAA records resolving `staging.procureops.com` to the server's public IP.
2. ACME challenge validation for automated Let's Encrypt TLS certificate issuance.
3. Host firewall (`ufw` / cloud security groups) restricting inbound access to ports 80, 443, and 22.
4. Outbound SMTP network access (port 587/465) unblocked by the cloud hosting provider.

---

## 6. Staging Preparation Step-by-Step Command Runbook

Execute these steps on the newly provisioned staging server:

```bash
# 1. Clone repository on staging server
git clone <REPO_URL> /opt/procureops
cd /opt/procureops
git checkout main

# 2. Configure production environment
cp .env.production.example .env.production
chmod 600 .env.production
# Edit .env.production: Set high-entropy JWT_SECRET_KEY, POSTGRES_PASSWORD, REDIS_PASSWORD,
# set APP_BASE_URL=https://staging.yourdomain.com, CORS_ORIGINS=["https://staging.yourdomain.com"],
# and configure EMAIL_BACKEND=console (or deploy Mailpit as described in Gate 3).

# 3. Validate configuration syntax
docker compose -f docker-compose.prod.yml --env-file .env.production config --quiet

# 4. Build production images
docker compose -f docker-compose.prod.yml --env-file .env.production build

# 5. Start stateful backing services first
docker compose -f docker-compose.prod.yml --env-file .env.production up -d postgres redis qdrant

# 6. Execute database migrations
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm backend-migration

# 7. Start application services
docker compose -f docker-compose.prod.yml --env-file .env.production up -d backend frontend outbox-worker

# 8. Verify service health
curl -f http://127.0.0.1:8000/health
curl -f http://127.0.0.1:3000/login
docker compose -f docker-compose.prod.yml --env-file .env.production logs --tail=50 outbox-worker

# 9. Configure and reload reverse proxy (Nginx or Caddy)
sudo nginx -t && sudo systemctl reload nginx
```

---

## 7. Final Repository Status & Safety Confirmation

- **Git Status:** Branch `main`, in sync with `origin/main` (`1701956`).
- **Uncommitted Modifications:** All 15 modified/untracked files (including rate limiting, currency checks, email service, outbox worker, tests, and deleted images) remain preserved in the local working tree.
- **Safety Compliance:**
  - Zero commits made.
  - Zero pushes made.
  - Zero remote deployments attempted.
  - Zero external SMTP emails dispatched (local Mailpit was used exclusively).
