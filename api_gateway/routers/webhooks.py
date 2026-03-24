from fastapi import APIRouter, Request, HTTPException
from typing import Dict, Any
import hmac
import hashlib
import os

router = APIRouter()

@router.post("/execution")
async def webhook_execution_result(request: Request):
    """
    Receive async execution results.
    
    Agents can POST results here when they've completed async work.
    """
    payload = await request.json()
    
    # Verify webhook signature if configured
    signature = request.headers.get("X-Webhook-Signature")
    if signature:
        await verify_signature(payload, signature)
    
    execution_id = payload.get("execution_id")
    result = payload.get("result")
    
    # Store result and notify waiting clients
    redis = request.app.state.redis
    await redis.setex(
        f"result:{execution_id}",
        3600,  # 1 hour TTL
        str(result)
    )
    
    return {"received": True}

@router.post("/agent/callback/{execution_id}")
async def agent_callback(execution_id: str, request: Request):
    """
    Callback endpoint for agents to report progress or completion.
    
    Used for long-running agent tasks.
    """
    data = await request.json()
    
    redis = request.app.state.redis
    
    # Update execution status
    await redis.hset(f"exec:{execution_id}", mapping={
        "status": data.get("status"),
        "progress": data.get("progress", 0),
        "message": data.get("message", ""),
        "result": str(data.get("result", {}))
    })
    
    return {"acknowledged": True}

async def verify_signature(payload: Dict[Any, Any], signature: str):
    """Verify webhook HMAC signature."""
    secret = os.getenv("WEBHOOK_SECRET", "")
    expected = hmac.new(
        secret.encode(),
        str(payload).encode(),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(f"sha256={expected}", signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
