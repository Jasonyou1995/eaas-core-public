import time
import json
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("eaas.audit")

class AuditMiddleware(BaseHTTPMiddleware):
    """
    Immutable audit logging middleware.
    
    Logs every request and response for compliance.
    """
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Capture request details
        audit_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "method": request.method,
            "path": request.url.path,
            "query": str(request.query_params),
            "ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", "unknown"),
        }
        
        # Add API key if present
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]
            # Log only prefix for privacy
            audit_entry["api_key_prefix"] = api_key[:8] + "..."
            request.state.api_key = api_key
        
        # Process request
        try:
            response = await call_next(request)
            audit_entry["status_code"] = response.status_code
            audit_entry["result"] = "success" if response.status_code < 400 else "error"
        except Exception as e:
            audit_entry["status_code"] = 500
            audit_entry["result"] = "exception"
            audit_entry["error"] = str(e)
            raise
        finally:
            # Calculate duration
            duration = int((time.time() - start_time) * 1000)
            audit_entry["duration_ms"] = duration
            
            # Store audit log
            await self._store_audit(request, audit_entry)
        
        return response
    
    async def _store_audit(self, request: Request, entry: dict):
        """Store audit entry to immutable log."""
        try:
            redis = request.app.state.redis
            audit_id = f"{entry['timestamp']}-{entry.get('api_key_prefix', 'anon')}"
            
            # Store in Redis with time-based key
            await redis.hset(f"audit:entry:{audit_id}", mapping={
                k: str(v) for k, v in entry.items()
            })
            await redis.zadd("audit:log", {audit_id: time.time()})
            
            # Also log to stdout for centralized logging
            logger.info(f"AUDIT: {json.dumps(entry)}")
            
        except Exception as e:
            # Never fail the request due to audit issues
            logger.error(f"Failed to store audit: {e}")
