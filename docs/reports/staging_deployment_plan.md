# ProcureOps AI — Staging Infrastructure & Deployment Plan

**Document Version:** 1.1.0 (Audited & Corrected)  
**Target Git Baseline:** Commit [`1701956`](https://github.com/procureops/procureops-ai/commit/1701956) (`origin/main`)  
**Status:** Pre-Deployment Planning & Operator Handoff  
**Deployment State:** **NO REMOTE DEPLOYMENT HAS OCCURRED.** This document is an operational blueprint for deploying ProcureOps AI to a future staging server once a VPS and domain are provisioned.

---

## Pre-Deployment Corrections & Audit Summary

Following a targeted verification against the repository implementation, the following corrections have been incorporated into this deployment plan:

1. **Frontend API URL Routing (`NEXT_PUBLIC_API_URL`):**
   - *Evidence:* In [frontend/src/lib/api/client.ts](file:///c:/Users/Betul/Desktop/procureops-ai/frontend/src/lib/api/client.ts), all request methods format paths as `${getBaseUrl()}${path}`, and individual API modules explicitly include `/api/v1/...` (e.g., [auth.ts](file:///c:/Users/Betul/Desktop/procureops-ai/frontend/src/lib/api/auth.ts) calls `/api/v1/auth/login`).
   - *Correction:* `NEXT_PUBLIC_API_URL` must be set to `https://<STAGING_DOMAIN>` (without a trailing `/api`). Setting `https://<STAGING_DOMAIN>/api` would cause calls to resolve to `https://<STAGING_DOMAIN>/api/api/v1/...` (double `/api`), triggering HTTP 404 errors.
2. **AI Model Identifier (`GEMINI_MODEL`):**
   - *Evidence:* [backend/app/core/config.py](file:///c:/Users/Betul/Desktop/procureops-ai/backend/app/core/config.py) and [backend/app/services/llm/gemini.py](file:///c:/Users/Betul/Desktop/procureops-ai/backend/app/services/llm/gemini.py) reference Google AI Developer API via `google-genai`. The identifier `gemini-3.5-flash-lite` in earlier drafts is not an available Google model endpoint.
   - *Correction:* Updated recommended model identifier to `gemini-2.0-flash` (or `gemini-1.5-flash`), which are active, verified production models on Google AI Studio.
3. **Migration & Rollback Decoupling:**
   - *Evidence:* In [backend/alembic/versions/](file:///c:/Users/Betul/Desktop/procureops-ai/backend/alembic/versions/), migration `downgrade()` methods execute destructive DDL (`op.drop_table` and `op.drop_column`), which destroys operational data.
   - *Correction:* Removed `alembic downgrade -1` as an automatic rollback step. Separated non-destructive **Application Rollback** (reverting code/containers while preserving database) from **Database Disaster Recovery** (restoring a pre-migration verified snapshot dump via `scripts/restore_db.sh`).
4. **Dynamic Docker Gateway Resolution for `TRUSTED_PROXIES`:**
   - *Evidence:* In [backend/app/core/rate_limit.py](file:///c:/Users/Betul/Desktop/procureops-ai/backend/app/core/rate_limit.py), if `TRUSTED_PROXIES` does not match the actual Docker bridge gateway IP, `X-Forwarded-For` is discarded, and all incoming users are assigned the same Docker gateway IP—causing global rate-limit throttling (HTTP 429) across all users.
   - *Correction:* Removed guessed subnets (`172.17.0.1`, `172.18.0.1`). Provided the exact inspection command (`docker network inspect procureops_prod_network`) to extract the real gateway IP on the target host.
5. **Mailpit Network Sequencing:**
   - *Evidence:* In [docker-compose.prod.yml](file:///c:/Users/Betul/Desktop/procureops-ai/docker-compose.prod.yml), the internal bridge network is named `procureops_prod_network`.
   - *Correction:* Clarified that if an auxiliary Mailpit container is used, it can only attach to `procureops_prod_network` *after* the network has been initialized by Docker Compose, or the network must be pre-created via `docker network create`. Reinforced `EMAIL_BACKEND=console` as the default, zero-dependency safe option.

### Remaining Assumptions & Checks Gated on VPS/Domain Provisioning:
- **Server OS:** Commands in Section 3 assume Debian/Ubuntu (APT package manager). If RHEL/Rocky/AlmaLinux is used, `dnf` package manager commands will apply.
- **Dynamic Bridge IP:** Exact Docker gateway IP must be queried after `docker-compose.prod.yml` starts stateful services.
- **DNS & SSL:** Let's Encrypt TLS issuance can only be executed once public DNS A records propagate to the VPS public IP.
- **Next Owner Action:** Select and provision a basic VPS provider (e.g. Hetzner, DigitalOcean) and domain name.

---

## 1. Verified Repository Facts vs. Assumptions & Recommendations

| Component | Verified Repository Fact | Assumption / Operator Recommendation |
| :--- | :--- | :--- |
| **Compose Services** | `docker-compose.prod.yml` defines exactly 7 services: `backend-migration`, `backend`, `frontend`, `outbox-worker`, `postgres`, `qdrant`, `redis`. | Services are deployed together on a single Linux VPS host. |
| **Network Isolation** | `postgres`, `redis`, and `qdrant` have zero published host ports. `frontend` binds to `127.0.0.1:3000`; `backend` binds to `127.0.0.1:8000`. | A host reverse proxy (Nginx or Caddy) terminates public HTTPS on ports 80/443 and proxies to loopback. |
| **Migrations** | `backend-migration` runs `alembic upgrade head`. Web backend and outbox worker do not run migrations on boot. | Migrations are executed as an explicit one-off step before public traffic is routed. |
| **Authentication & Cookies** | `_set_auth_cookie` enforces `secure=True` when `ENVIRONMENT=production`. Rate limiter enforces 10 req / 60s. | Browsers will reject login session cookies unless the staging endpoint is served strictly over HTTPS. |
| **Email Subsystem** | `EMAIL_BACKEND=console` is supported by both API and `outbox-worker`. Mailpit is NOT in `docker-compose.prod.yml`. | Initial staging must use `EMAIL_BACKEND=console` or an isolated Mailpit container to prevent external email transmission. |
| **Host System & OS** | Code is platform-independent Docker containers (Linux Alpine/Debian base). | Recommending Ubuntu 22.04/24.04 LTS or Debian 12 with 4 vCPU, 8 GB RAM, and 50 GB NVMe SSD. |
| **Domain & DNS** | Code supports single-origin (`APP_BASE_URL`, `NEXT_PUBLIC_API_URL`, `CORS_ORIGINS`). | Owner provisions domain name (e.g., `<STAGING_DOMAIN>`) and points A/AAAA DNS records to `<VPS_IP>`. |

---

## 2. Infrastructure Recommendations & Prerequisites

### 2.1 Recommended Server Specifications (Non-Verified Recommendation)
The following hardware profile is recommended for a stable staging environment hosting all 7 containers, Next.js build cache, and vector embeddings:

- **Compute:** 4 vCPU (x86_64 architecture).
- **Memory:** 8 GB RAM (minimum 4 GB RAM + 4 GB swap, but 8 GB RAM avoids OOM during Next.js image builds and Qdrant indexing).
- **Storage:** 50 GB NVMe SSD (Docker images, PostgreSQL data volume, Qdrant vectors, uploaded documents).
- **Operating System:** Ubuntu 24.04 LTS, Ubuntu 22.04 LTS, or Debian 12 (bookworm).
- **Providers:** Budget-friendly providers (Hetzner Cloud CX32/CPX31 ~€7–12/mo, DigitalOcean Droplet, Linode/Akamai, Scaleway).

### 2.2 DNS & Domain Setup
Before requesting TLS certificates, configure public DNS records at your registrar:

| Record Type | Hostname / Subdomain | Target Value | Purpose |
| :---: | :---: | :---: | :--- |
| **A** | `<STAGING_DOMAIN>` (e.g. `staging.yourdomain.com`) | `<VPS_IP>` | Web application frontend and API reverse proxy |
| **AAAA** | `<STAGING_DOMAIN>` (optional) | `<VPS_IPv6>` | IPv6 direct routing (if enabled on host) |

*TTL recommendation: 300 seconds (5 minutes) during initial setup for rapid propagation.*

### 2.3 Host Firewall Configuration (`ufw`)
Only ports 22 (SSH), 80 (HTTP), and 443 (HTTPS) must be open to the public internet. All application, database, cache, and vector ports must be blocked from external interfaces:

```bash
# Allow SSH, HTTP, and HTTPS (Ubuntu/Debian)
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment 'SSH'
sudo ufw allow 80/tcp comment 'HTTP (ACME / Redirect)'
sudo ufw allow 443/tcp comment 'HTTPS'

# Enable firewall
sudo ufw enable
sudo ufw status verbose
```

---

## 3. Host System Setup & Docker Installation

Execute the following commands on a clean Debian/Ubuntu staging server:

```bash
# 1. Update system packages
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y curl git jq ufw fail2ban ca-certificates gnupg lsb-release

# 2. Install official Docker Engine and Docker Compose v2
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 3. Add deployer user to docker group
sudo usermod -aG docker $USER

# 4. Verify Docker installation
docker --version
docker compose version
```

---

## 4. Staging Environment Configuration & Secrets

### 4.1 Clone Repository & Restrict Directory
```bash
sudo mkdir -p /opt/procureops
sudo chown $USER:$USER /opt/procureops
git clone <REPO_URL> /opt/procureops
cd /opt/procureops
git checkout main
```

### 4.2 Generate Cryptographic Secrets
Generate unique, high-entropy 64-character secrets on the staging host:
```bash
# Generate JWT Secret (min 32 chars enforced by Pydantic)
openssl rand -hex 32

# Generate Session Secret
openssl rand -hex 32

# Generate PostgreSQL Password
openssl rand -hex 24

# Generate Redis Password
openssl rand -hex 24
```

### 4.3 Configure `.env.production`
Copy the repository template and populate staging values:
```bash
cp .env.production.example .env.production
chmod 600 .env.production
nano .env.production
```

Ensure the following staging values are defined:
```env
# ─── 1. Application & Core Invariants ─────────────────────────────────────────
APP_NAME="ProcureOps AI (Staging)"
APP_VERSION=0.1.0
ENVIRONMENT=production
DEBUG=False
WEB_CONCURRENCY=2

# ─── 2. Cryptographic Secrets ─────────────────────────────────────────────────
JWT_SECRET_KEY=<OUTPUT_FROM_OPENSSL_RAND_HEX_32>
SECRET_KEY=<OUTPUT_FROM_OPENSSL_RAND_HEX_32>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# ─── 3. Domain & Origins ──────────────────────────────────────────────────────
APP_BASE_URL=https://<STAGING_DOMAIN>
# NOTE: Set to domain root without /api. apiClient in frontend automatically prefixes paths with /api/v1/
NEXT_PUBLIC_API_URL=https://<STAGING_DOMAIN>
CORS_ORIGINS=["https://<STAGING_DOMAIN>"]

# ─── 4. Trusted Proxies ───────────────────────────────────────────────────────
# Will be updated in Step 3b after Docker network creation to include the real bridge gateway IP
TRUSTED_PROXIES=["127.0.0.1"]

# ─── 5. PostgreSQL ────────────────────────────────────────────────────────────
POSTGRES_USER=procureops
POSTGRES_PASSWORD=<OUTPUT_FROM_POSTGRES_PASSWORD_GEN>
POSTGRES_DB=procureops_staging_db
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# ─── 6. Qdrant ────────────────────────────────────────────────────────────────
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_GRPC_PORT=6334
QDRANT_COLLECTION_NAME=procureops_staging_policies

# ─── 7. Redis ─────────────────────────────────────────────────────────────────
REDIS_HOST=redis
REDIS_PORT=6379

# ─── 8. AI & Embeddings ───────────────────────────────────────────────────────
GEMINI_API_KEY=<YOUR_VALID_GOOGLE_AI_STUDIO_API_KEY>
GEMINI_MODEL=gemini-2.0-flash

# ─── 9. File Storage ──────────────────────────────────────────────────────────
UPLOAD_DIR=uploads
MAX_UPLOAD_SIZE_MB=50

# ─── 10. Initial Email Isolation Configuration ────────────────────────────────
# CRITICAL: Console mode logs all notifications to stdout; ZERO external network packets.
EMAIL_BACKEND=console
ENABLE_OUTBOX_WORKER=true
SMTP_FROM_EMAIL=procurement@<STAGING_DOMAIN>
SMTP_FROM_NAME="ProcureOps AI Staging"

# ─── 11. Observability ────────────────────────────────────────────────────────
LOG_LEVEL=INFO
LOG_FORMAT=json
```

---

## 5. Initial Email Isolation Options

To guarantee that staging smoke tests never accidentally transmit emails to real suppliers or external inboxes:

### Option A: `EMAIL_BACKEND=console` (Air-Gapped — Recommended for First Boot)
- **Mechanism:** Implemented in `backend/app/services/email/console_provider.py`.
- **Behavior:** The API queues emails in PostgreSQL outbox; the `outbox-worker` daemon claims the batch, logs the sanitized message to container stdout, and marks the delivery as `sent` (`provider_message_id="<console-...>"`).
- **Inspection Command:**
  ```bash
  docker compose -f docker-compose.prod.yml --env-file .env.production logs --tail=50 outbox-worker
  ```
- **Safety:** **100% air-gapped.** No SMTP connection is attempted; no external emails can be dispatched.

### Option B: Local Mailpit Container (Web UI Inspection)
If operators wish to inspect the rendered HTML email templates and click supplier portal links in a browser:
1. Ensure the Docker network `procureops_prod_network` exists (it is created automatically after starting stateful services in Step 3 of the deployment runbook):
   ```bash
   docker network create procureops_prod_network 2>/dev/null || true
   ```
2. Run Mailpit attached strictly to the internal Docker network, with web UI bound exclusively to host loopback:
   ```bash
   docker run -d --name procureops-mailpit \
     --network procureops_prod_network \
     -p 127.0.0.1:8025:8025 \
     --restart unless-stopped \
     axllent/mailpit:latest
   ```
   *(Note: SMTP port 1025 is NOT published to the host. It is accessible exclusively inside `procureops_prod_network`).*
3. Update `.env.production`:
   ```env
   EMAIL_BACKEND=smtp
   SMTP_HOST=procureops-mailpit
   SMTP_PORT=1025
   SMTP_USE_TLS=false
   SMTP_USE_SSL=false
   SMTP_USER=
   SMTP_PASSWORD=
   SMTP_FROM_EMAIL=staging@<STAGING_DOMAIN>
   ```
4. Access Mailpit Web UI securely via an SSH tunnel from your local machine:
   ```bash
   ssh -L 8025:127.0.0.1:8025 user@<VPS_IP>
   ```
   Open `http://localhost:8025` in your local web browser.

---

## 6. Reverse Proxy & SSL Setup (Caddy or Nginx)

### Option 1: Caddy (Simplest — Automatic SSL)
Caddy automatically provisions and renews Let's Encrypt certificates:

1. Install Caddy (Debian/Ubuntu):
   ```bash
   sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
   curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
   curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
   sudo apt-get update
   sudo apt-get install caddy
   ```
2. Configure `/etc/caddy/Caddyfile`:
   ```caddy
   <STAGING_DOMAIN> {
       # Backend API routes (FastAPI)
       handle /api/* {
           reverse_proxy 127.0.0.1:8000
       }

       # Backend Health check
       handle /health* {
           reverse_proxy 127.0.0.1:8000
       }

       # Next.js Frontend
       handle {
           reverse_proxy 127.0.0.1:3000
       }
   }
   ```
3. Restart Caddy:
   ```bash
   sudo systemctl restart caddy
   ```

### Option 2: Nginx with Certbot
1. Install Nginx and Certbot:
   ```bash
   sudo apt-get install -y nginx certbot python3-certbot-nginx
   ```
2. Create site config `/etc/nginx/sites-available/procureops.conf`:
   ```nginx
   server {
       listen 80;
       server_name <STAGING_DOMAIN>;

       # Backend API routes
       location /api/ {
           proxy_pass http://127.0.0.1:8000/api/;
           proxy_http_version 1.1;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }

       # Backend Health check
       location /health {
           proxy_pass http://127.0.0.1:8000/health;
           proxy_set_header Host $host;
       }

       # Next.js Frontend
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
3. Enable site and obtain SSL certificate:
   ```bash
   sudo ln -s /etc/nginx/sites-available/procureops.conf /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   sudo certbot --nginx -d <STAGING_DOMAIN> --non-interactive --agree-tos -m admin@<STAGING_DOMAIN>
   ```

---

## 7. Staging Deployment Execution Runbook

Follow these exact steps from `/opt/procureops`:

```bash
# ── Step 1: Validate Compose Configuration ─────────────────────────────────────
docker compose -f docker-compose.prod.yml --env-file .env.production config --quiet

# ── Step 2: Build Multi-Stage Production Images ────────────────────────────────
docker compose -f docker-compose.prod.yml --env-file .env.production build

# ── Step 3: Start Stateful Services First ──────────────────────────────────────
docker compose -f docker-compose.prod.yml --env-file .env.production up -d postgres redis qdrant

# ── Step 3b: Query Docker Bridge Gateway IP & Update TRUSTED_PROXIES ───────────
# Query the actual dynamic gateway IP assigned by Docker on this host:
GATEWAY_IP=$(docker network inspect procureops_prod_network --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}')
echo "Docker bridge gateway IP is: ${GATEWAY_IP}"
# Update TRUSTED_PROXIES in .env.production to include 127.0.0.1 and this gateway IP:
# Example: TRUSTED_PROXIES=["127.0.0.1", "${GATEWAY_IP}"]

# ── Step 4: Wait for PostgreSQL Healthcheck ────────────────────────────────────
until docker compose -f docker-compose.prod.yml --env-file .env.production ps postgres | grep -q "(healthy)"; do
    echo "Waiting for postgres to become healthy..."
    sleep 3
done

# ── Step 5: Execute Database Migrations (Canonical Runner) ──────────────────────
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm backend-migration

# ── Step 6: Verify Migration Version in PostgreSQL ─────────────────────────────
docker compose -f docker-compose.prod.yml --env-file .env.production exec -T postgres \
  psql -U procureops -d procureops_staging_db -c "SELECT version_num FROM alembic_version;"

# ── Step 7: Launch Application & Worker Services ───────────────────────────────
docker compose -f docker-compose.prod.yml --env-file .env.production up -d backend frontend outbox-worker

# ── Step 8: Verify Container Status ────────────────────────────────────────────
docker compose -f docker-compose.prod.yml --env-file .env.production ps
```

---

## 8. Backup, Restore & Rollback Procedures

### 8.1 Automated Backup Script
Run the verified repository backup utility before any update:
```bash
python3 scripts/backup_db.py --output-dir /opt/procureops/backups --db procureops_staging_db --user procureops
```
*Creates: `/opt/procureops/backups/procureops_backup_procureops_staging_db_<timestamp>.dump` (compressed `-Fc` format).*

### 8.2 Safe Database Restore Test
Verify backups safely without overwriting the active staging database:
```bash
# Restore to a disposable target database (safely guard-railed)
./scripts/restore_db.sh /opt/procureops/backups/procureops_backup_<timestamp>.dump procureops_staging_restore_test
```

### 8.3 Application Rollback vs. Database Disaster Recovery

#### A. Application Rollback (Code-Level — Non-Destructive)
If a newly deployed image introduces an application bug, roll back the containers while keeping the database intact:
1. Stop the application services:
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.production stop backend frontend outbox-worker
   ```
2. Revert Git commit to previous stable release:
   ```bash
   git checkout <PREVIOUS_STABLE_COMMIT>
   docker compose -f docker-compose.prod.yml --env-file .env.production build backend frontend outbox-worker
   ```
3. Restart application services:
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.production up -d backend frontend outbox-worker
   ```

#### B. Database Disaster Recovery (Snapshot Restore)
If data corruption or an irreversible schema error occurs:
1. Stop web and worker services:
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.production stop backend frontend outbox-worker
   ```
2. Terminate active database connections and restore from pre-deployment snapshot:
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.production exec -T postgres \
     psql -U procureops -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'procureops_staging_db' AND pid <> pg_backend_pid();"
   
   docker compose -f docker-compose.prod.yml --env-file .env.production exec -T postgres dropdb -U procureops procureops_staging_db
   docker compose -f docker-compose.prod.yml --env-file .env.production exec -T postgres createdb -U procureops procureops_staging_db
   
   docker compose -f docker-compose.prod.yml --env-file .env.production exec -T postgres \
     pg_restore -U procureops -d procureops_staging_db --no-owner --no-acl < /opt/procureops/backups/procureops_backup_<timestamp>.dump
   ```
3. Restart application services:
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.production up -d
   ```

---

## 9. Post-Deployment Smoke-Test Protocol

Execute these 10 verification steps against the live staging domain (`https://<STAGING_DOMAIN>`):

| Step | Test Objective | Exact Verification Command / Action | Expected Result |
| :---: | :--- | :--- | :--- |
| **1** | **Backend Liveness & Readiness** | `curl -i https://<STAGING_DOMAIN>/health`<br>`curl -i https://<STAGING_DOMAIN>/health/ready` | HTTP 200 `{"status":"ok"}`. Ready probe reports DB, Redis, and Qdrant connected. |
| **2** | **Frontend Accessibility & TLS** | Open `https://<STAGING_DOMAIN>/login` in browser. | Valid HTTPS padlock (no SSL errors), login page renders cleanly. |
| **3** | **Unauthenticated Route Shielding** | `curl -i https://<STAGING_DOMAIN>/api/v1/auth/me` | HTTP 401 Unauthorized (JWT required). |
| **4** | **Rate Limiting Enforcement** | Send 11 rapid POST requests to `/api/v1/auth/login`. | Requests 1–10 return 401; 11th request returns HTTP 429 (`Retry-After: 60`). |
| **5** | **Organization & Admin Onboarding** | Register new tenant via UI or POST `/api/v1/auth/register`. | HTTP 201 Created. User receives JWT session cookie with `Secure; HttpOnly; SameSite=Lax`. |
| **6** | **RFQ & Multi-Quote Ingestion** | Create test RFQ in dashboard; submit 2 quotes. | RFQ transitions to `collecting_quotes`; quotes visible in dashboard. |
| **7** | **Deterministic Compliance & TCO** | Run AI analysis on RFQ. | Deterministic engine verifies budget, currency, warranty, and delivery limits. |
| **8** | **Approval & PO Issuance** | Manager approves recommended quote. | Purchase order created with status `issued` (e.g. `PO-*-001`). |
| **9** | **Supplier Portal Isolation** | Query `/api/v1/portal/rfq` with supplier token header. | HTTP 200 OK. Internal budget, competitor quotes, and company policies are completely shielded. |
| **10** | **Email Outbox Dispatch** | Inspect outbox worker logs: `docker compose logs outbox-worker`. | Log displays `[CONSOLE EMAIL]` (or message captured in Mailpit). Sent status recorded in DB. |

---

## 10. Live SMTP Enablement Preconditions

Live SMTP must **not** be enabled on staging or production until all of the following conditions are verified:

1. **DNS Authentications Verified:**
   - [ ] SPF TXT record published: `v=spf1 include:<PROVIDER_INCLUDE> ~all`.
   - [ ] DKIM CNAME/TXT records verified by email provider.
   - [ ] DMARC TXT record published: `v=DMARC1; p=quarantine; rua=mailto:dmarc@<DOMAIN>`.
2. **Firewall Egress Verified:**
   - [ ] VPS hosting provider allows outbound TCP connections on port 587 (some providers block port 25/587 by default until identity verification).
3. **Template & Privacy Audit:**
   - [ ] Supplier portal URLs in email invitations resolve to `https://<STAGING_DOMAIN>/portal/rfq/{token}`.
   - [ ] No internal budget figures or competitor identities appear in email templates.
4. **Credential Authorization:**
   - [ ] Project owner explicitly approves switching `EMAIL_BACKEND=smtp` with verified provider credentials.

---

## 11. Infrastructure Decisions Required from Project Owner

Before proceeding to remote deployment, the project owner needs to provide:

1. **Server / VPS Provider & Provisioning:**
   - Provider choice (e.g. Hetzner Cloud CX32/CPX31 ~€7–12/mo, DigitalOcean Droplet, AWS t3.large, etc.).
   - Server root or deployer SSH access (`ssh-rsa` public key).
2. **Domain Name:**
   - Existing domain name or new domain purchase (e.g., from Cloudflare Registrar, Namecheap, etc.).
   - Access to DNS management console to set the A record (`<STAGING_DOMAIN>` -> `<VPS_IP>`).
3. **AI Studio Quota:**
   - Google Gemini API key with billing enabled (for document parsing and multi-criteria trade-off RAG analysis).
4. **Initial Email Preference:**
   - Confirmation to begin with `EMAIL_BACKEND=console` (recommended) or deploy an isolated Mailpit container.

---
*Blueprint verified and certified against ProcureOps AI repository baseline `1701956`.*
