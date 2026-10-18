"""
app/core/rate_limit.py

Sliding-window rate limiter and abuse protection for public unauthenticated endpoints (Phase 14).
Supports Redis when reachable, with automatic in-memory sliding window fallback.
"""

import time
import logging
from collections import defaultdict
import ipaddress
from typing import Callable, Optional, Sequence
from fastapi import Request, HTTPException, status
from app.core.config import settings

logger = logging.getLogger("app.rate_limit")

# In-memory sliding-window storage fallback: {key: [timestamp_1, timestamp_2, ...]}
_memory_store: dict[str, list[float]] = defaultdict(list)
_LAST_CLEANUP = time.time()


def _is_ip_in_trusted(ip_str: str, trusted_networks: Sequence[ipaddress.IPv4Network | ipaddress.IPv6Network]) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str.strip())
        return any(ip in net for net in trusted_networks)
    except ValueError:
        return False


def resolve_client_ip(request: Request, trusted_proxies: Optional[Sequence[str]] = None) -> str:
    """
    Safely resolves the true client IP address, guarding against header spoofing (Phase 16.2).

    Security model:
    1. If request.client is None or empty, return 'unknown'.
    2. Direct connection peer is peer_ip = request.client.host.
    3. If trusted_proxies is None, settings.TRUSTED_PROXIES is used.
    4. If no trusted proxies are configured (empty sequence, the default), direct peer_ip is returned.
       Arbitrary X-Forwarded-For headers from public clients are strictly ignored.
    5. If peer_ip is NOT within the configured trusted proxy CIDRs/IPs,
       the direct peer_ip is returned, and X-Forwarded-For is ignored.
    6. If peer_ip IS trusted:
       Parse X-Forwarded-For entries from right to left (the path the request traveled).
       The rightmost untrusted IP address in the chain is the authentic client IP.
       Any malformed or invalid IP addresses trigger a safe fallback to peer_ip.
    """
    if not request.client or not request.client.host:
        return "unknown"

    peer_ip = request.client.host.strip()

    if trusted_proxies is None:
        trusted_proxies = getattr(settings, "TRUSTED_PROXIES", [])

    if not trusted_proxies:
        return peer_ip

    # Parse trusted networks (fail-safe on malformed configuration)
    trusted_networks = []
    for tp in trusted_proxies:
        try:
            trusted_networks.append(ipaddress.ip_network(str(tp).strip(), strict=False))
        except ValueError:
            logger.warning("Geçersiz TRUSTED_PROXIES girdisi atlandı: %s", tp)

    if not trusted_networks:
        return peer_ip

    # Check if direct connection peer is trusted
    if not _is_ip_in_trusted(peer_ip, trusted_networks):
        return peer_ip

    forwarded = request.headers.get("X-Forwarded-For")
    if not forwarded:
        return peer_ip

    # Walk right-to-left
    raw_ips = [item.strip() for item in forwarded.split(",") if item.strip()]
    if not raw_ips:
        return peer_ip

    # Right-to-left traversal: find the first IP that is NOT in trusted_networks
    for ip_str in reversed(raw_ips):
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            # Malformed IP in header -> possible attack/tampering, fail-safe to peer_ip
            logger.warning("X-Forwarded-For başlığında geçersiz IP tespit edildi: %s", ip_str[:50])
            return peer_ip

        if not any(ip_obj in net for net in trusted_networks):
            return str(ip_obj)

    # If all IPs in X-Forwarded-For are in trusted networks, the leftmost valid IP is the originator
    return raw_ips[0]


def _cleanup_memory_store(now: float, window_seconds: int = 60) -> None:
    global _LAST_CLEANUP
    if now - _LAST_CLEANUP < 300:  # Cleanup every 5 minutes
        return
    _LAST_CLEANUP = now
    cutoff = now - window_seconds
    keys_to_delete = []
    for k, timestamps in list(_memory_store.items()):
        valid = [t for t in timestamps if t > cutoff]
        if not valid:
            keys_to_delete.append(k)
        else:
            _memory_store[k] = valid
    for k in keys_to_delete:
        _memory_store.pop(k, None)


def rate_limit(max_requests: int = 60, window_seconds: int = 60) -> Callable:
    """
    FastAPI dependency factory enforcing rate limits by client IP.
    Usage:
        @router.get("/portal/rfq", dependencies=[Depends(rate_limit(max_requests=60, window_seconds=60))])
    """
    async def dependency(request: Request) -> None:
        client_ip = resolve_client_ip(request)

        now = time.time()
        route_path = request.url.path
        key = f"rl:{route_path}:{client_ip}"

        # 1. Try Redis if host is configured
        redis_success = False
        try:
            import redis.asyncio as aioredis
            redis_client = aioredis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0",
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
            )
            pipe = redis_client.pipeline()
            # Redis sliding window using sorted sets
            pipe.zremrangebyscore(key, 0, now - window_seconds)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window_seconds + 5)
            results = await pipe.execute()
            await redis_client.aclose()

            count = results[2]
            redis_success = True
            if count > max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Çok fazla istek gönderildi. Lütfen bir süre sonra tekrar deneyiniz.",
                    headers={"Retry-After": str(window_seconds)},
                )
        except HTTPException:
            raise
        except Exception:
            redis_success = False

        # 2. In-memory fallback if Redis is unreachable
        if not redis_success:
            _cleanup_memory_store(now, window_seconds)
            timestamps = _memory_store[key]
            cutoff = now - window_seconds
            timestamps = [t for t in timestamps if t > cutoff]
            if len(timestamps) >= max_requests:
                _memory_store[key] = timestamps
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Çok fazla istek gönderildi. Lütfen bir süre sonra tekrar deneyiniz.",
                    headers={"Retry-After": str(window_seconds)},
                )
            timestamps.append(now)
            _memory_store[key] = timestamps

    return dependency
