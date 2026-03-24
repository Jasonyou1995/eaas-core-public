from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import uuid
import time

router = APIRouter()

class AgentExecuteRequest(BaseModel):
    agent_type: str = Field(..., description="Plugin agent type (e.g., sample.price_feed)")
    params: Dict[str, Any] = Field(default={}, description="Agent-specific parameters")
    priority: int = Field(default=5, ge=1, le=10, description="Execution priority (1-10)")
    timeout: int = Field(default=30, ge=5, le=300, description="Timeout in seconds")
    callback_url: Optional[str] = Field(None, description="Optional webhook for async results")

class AgentExecuteResponse(BaseModel):
    execution_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None
    audit_id: str

@router.post("/execute", response_model=AgentExecuteResponse)
async def execute_agent(
    request: Request,
    background_tasks: BackgroundTasks,
    exec_request: AgentExecuteRequest
):
    """
    Execute an agent with the specified parameters.
    
    The agent runs in an isolated container with scoped permissions.
    """
    orchestrator = request.app.state.orchestrator
    permissions = request.app.state.permissions
    
    execution_id = str(uuid.uuid4())
    audit_id = str(uuid.uuid4())
    start_time = time.time()
    
    # Check permissions
    await permissions.validate_agent_access(
        api_key=request.state.api_key,
        agent_type=exec_request.agent_type
    )
    
    try:
        # Execute agent in sandbox
        result = await orchestrator.execute(
            execution_id=execution_id,
            agent_type=exec_request.agent_type,
            params=exec_request.params,
            timeout=exec_request.timeout,
            audit_id=audit_id
        )
        
        execution_time = int((time.time() - start_time) * 1000)
        
        return AgentExecuteResponse(
            execution_id=execution_id,
            status="success",
            result=result,
            execution_time_ms=execution_time,
            audit_id=audit_id
        )
        
    except Exception as e:
        execution_time = int((time.time() - start_time) * 1000)
        
        return AgentExecuteResponse(
            execution_id=execution_id,
            status="error",
            error=str(e),
            execution_time_ms=execution_time,
            audit_id=audit_id
        )

@router.post("/execute/async")
async def execute_agent_async(
    request: Request,
    background_tasks: BackgroundTasks,
    exec_request: AgentExecuteRequest
):
    """
    Queue an agent for asynchronous execution.
    
    Results will be sent to the callback_url if provided,
    or can be retrieved via the status endpoint.
    """
    orchestrator = request.app.state.orchestrator
    
    execution_id = str(uuid.uuid4())
    audit_id = str(uuid.uuid4())
    
    # Queue for background execution
    await orchestrator.queue_async(
        execution_id=execution_id,
        agent_type=exec_request.agent_type,
        params=exec_request.params,
        callback_url=exec_request.callback_url,
        audit_id=audit_id
    )
    
    return {
        "execution_id": execution_id,
        "status": "queued",
        "audit_id": audit_id,
        "status_url": f"/v1/agents/status/{execution_id}"
    }

@router.get("/status/{execution_id}")
async def get_execution_status(execution_id: str, request: Request):
    """Get the status of a queued or running agent execution."""
    orchestrator = request.app.state.orchestrator
    
    status = await orchestrator.get_status(execution_id)
    if not status:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    return status

@router.get("/list")
async def list_available_agents(request: Request):
    """List all available agent plugins."""
    orchestrator = request.app.state.orchestrator
    
    agents = await orchestrator.list_agents()
    return {"agents": agents}

@router.get("/{agent_type}/schema")
async def get_agent_schema(agent_type: str, request: Request):
    """Get the input schema for a specific agent type."""
    orchestrator = request.app.state.orchestrator
    
    schema = await orchestrator.get_agent_schema(agent_type)
    if not schema:
        raise HTTPException(status_code=404, detail="Agent type not found")
    
    return schema
