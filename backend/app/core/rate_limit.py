"""
app/core/rate_limit.py

Sliding-window rate limiter and abuse protection for public unauthenticated endpoints (Phase 14).
Supports Redis when reachable, with automatic in-memory sliding window fallback.
"""

import time
import logging
from collections import defaultdict
from typing import Callable
from fastapi import Request, HTTPException, status
from app.core.config import settings

logger = logging.getLogger("app.rate_limit")

# In-memory sliding-window storage fallback: {key: [timestamp_1, timestamp_2, ...]}
_memory_store: dict[str, list[float]] = defaultdict(list)
_LAST_CLEANUP = time.time()


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
        client_ip = request.client.host if request.client else "unknown"
        # Forwarded-For support for proxies
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()

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
