from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

router = APIRouter()

class AuditLogEntry(BaseModel):
    id: str
    timestamp: str
    api_key: str
    action: str
    agent_type: Optional[str]
    execution_id: Optional[str]
    ip_address: str
    user_agent: str
    result: str
    execution_time_ms: Optional[int]

@router.get("/audit", response_model=List[AuditLogEntry])
async def get_audit_logs(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    api_key: Optional[str] = None
):
    """
    Retrieve audit logs for compliance and debugging.
    
    Requires admin access.
    """
    redis = request.app.state.redis
    
    # In production: query from immutable storage (S3, ClickHouse, etc.)
    # This is a simplified implementation
    logs = []
    
    # Query from Redis sorted set
    audit_keys = await redis.zrevrange("audit:log", offset, offset + limit - 1)
    
    for key in audit_keys:
        log_data = await redis.hgetall(f"audit:entry:{key}")
        if log_data:
            logs.append(AuditLogEntry(**log_data))
    
    return logs

@router.get("/stats")
async def get_platform_stats(request: Request):
    """Get platform usage statistics."""
    redis = request.app.state.redis
    orchestrator = request.app.state.orchestrator
    
    # Aggregate stats
    total_executions = await redis.get("stats:total_executions") or 0
    active_agents = len(await orchestrator.list_agents())
    
    return {
        "total_executions": int(total_executions),
        "active_agents": active_agents,
        "platform_uptime_hours": 0,  # Calculate from service start
        "avg_execution_time_ms": 0,  # Calculate from audit logs
        "top_agents": [],  # Aggregated from executions
        "system_status": "operational"
    }

@router.post("/agents/{agent_type}/disable")
async def disable_agent(agent_type: str, request: Request):
    """Temporarily disable an agent type."""
    orchestrator = request.app.state.orchestrator
    await orchestrator.disable_agent(agent_type)
    
    return {"status": "disabled", "agent_type": agent_type}

@router.post("/agents/{agent_type}/enable")
async def enable_agent(agent_type: str, request: Request):
    """Re-enable a disabled agent type."""
    orchestrator = request.app.state.orchestrator
    await orchestrator.enable_agent(agent_type)
    
    return {"status": "enabled", "agent_type": agent_type}

@router.get("/system/info")
async def get_system_info():
    """Get system configuration information."""
    return {
        "version": "1.0.0",
        "environment": "production",
        "docker_version": "24.0+",
        "security_features": [
            "non_root_containers",
            "seccomp_profiles",
            "network_isolation",
            "readonly_rootfs"
        ]
    }
