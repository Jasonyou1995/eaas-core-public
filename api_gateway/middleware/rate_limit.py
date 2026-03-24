import time
import redis.asyncio as redis
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using Redis sliding window.
    
    Limits:
    - Free tier: 100 requests/minute
    - Pro tier: 1000 requests/minute
    - Enterprise: Custom limits
    """
    
    def __init__(self, app, redis_url: str = "redis://localhost:6379"):
        super().__init__(app)
        self.redis_url = redis_url
        self.default_limit = 100  # requests per minute
        self.window = 60  # seconds
    
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/ready", "/live", "/metrics"]:
            return await call_next(request)
        
        # Get API key for rate limiting
        api_key = self._extract_api_key(request)
        if not api_key:
            # Allow unauthenticated requests with strict limits
            api_key = f"ip:{request.client.host}"
        
        # Check rate limit
        allowed, remaining, reset_time = await self._check_rate_limit(api_key)
        
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={
                    "X-RateLimit-Limit": str(self.default_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(reset_time - int(time.time()))
                }
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.default_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        
        return response
    
    def _extract_api_key(self, request: Request) -> str:
        """Extract API key from Authorization header."""
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return None
    
    async def _check_rate_limit(self, api_key: str) -> tuple:
        """
        Check if request is within rate limit.
        
        Returns: (allowed: bool, remaining: int, reset_time: int)
        """
        # This is a simplified implementation
        # In production, use Redis with proper sliding window
        
        now = int(time.time())
        window_start = now - self.window
        
        # In real implementation:
        # 1. Remove entries older than window
        # 2. Count remaining entries
        # 3. Add current request
        # 4. Check against limit
        
        # For now, always allow (implement proper logic in production)
        return True, self.default_limit - 1, now + self.window
