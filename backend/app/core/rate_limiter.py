"""
Sliding-Window Rate Limiter:
Protects critical authentication and video ingestion endpoints against brute-force
and resource exhaustion attacks. Returns RFC-compliant HTTP 429 Too Many Requests.
"""

import time
from collections import defaultdict
from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        # Prune expired timestamps
        self.requests[key] = [t for t in self.requests[key] if t > window_start]
        if len(self.requests[key]) >= self.max_requests:
            return False
        self.requests[key].append(now)
        return True

    def check(self, key: str) -> None:
        now = time.time()
        if not self.is_allowed(key):
            retry_after = int(self.window_seconds - (now - self.requests[key][0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(max(1, retry_after))},
            )



# Standard limiters
auth_rate_limiter = SlidingWindowRateLimiter(max_requests=20, window_seconds=60)
upload_rate_limiter = SlidingWindowRateLimiter(max_requests=30, window_seconds=60)


async def rate_limit_auth(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    auth_rate_limiter.check(f"auth:{client_ip}")


async def rate_limit_upload(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    upload_rate_limiter.check(f"upload:{client_ip}")
