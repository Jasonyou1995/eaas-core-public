import asyncio
import logging
import os
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

from core_engine.sandbox import SandboxManager
from core_engine.registry import PluginRegistry
from core_engine.permissions import PermissionEngine

logger = logging.getLogger("eaas.orchestrator")

@dataclass
class ExecutionResult:
    execution_id: str
    status: str
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    duration_ms: int
    audit_id: str

class AgentOrchestrator:
    """
    Central orchestrator for agent lifecycle management.
    
    Responsibilities:
    - Plugin discovery and loading
    - Execution queue management
    - Sandbox container lifecycle
    - Result aggregation and logging
    """
    
    def __init__(self, redis):
        self.redis = redis
        self.sandbox = SandboxManager()
        self.registry = PluginRegistry()
        self.running = False
        self._execution_queue = asyncio.Queue()
        self._worker_tasks = []
    
    async def initialize(self):
        """Initialize the orchestrator."""
        logger.info("Initializing AgentOrchestrator...")
        
        # Load plugins from both public and private directories
        await self.registry.discover_plugins([
            "/app/sample_plugins",
            "/app/private"  # Mounted from eaas-plugins-private
        ])
        
        # Start worker tasks
        self.running = True
        for i in range(int(os.getenv("WORKER_COUNT", 4))):
            task = asyncio.create_task(self._worker_loop(f"worker-{i}"))
            self._worker_tasks.append(task)
        
        logger.info(f"Orchestrator initialized with {len(self._worker_tasks)} workers")
    
    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down AgentOrchestrator...")
        self.running = False
        
        # Wait for workers to finish current tasks
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        
        # Clean up sandboxes
        await self.sandbox.cleanup_all()
    
    async def execute(
        self,
        execution_id: str,
        agent_type: str,
        params: Dict[str, Any],
        timeout: int,
        audit_id: str
    ) -> Dict[str, Any]:
        """
        Execute an agent synchronously.
        
        Args:
            execution_id: Unique execution identifier
            agent_type: Plugin agent type (e.g., sample.price_feed)
            params: Agent-specific parameters
            timeout: Maximum execution time in seconds
            audit_id: Audit trail identifier
        
        Returns:
            Execution result dictionary
        """
        # Get agent manifest
        manifest = await self.registry.get_manifest(agent_type)
        if not manifest:
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        # Execute in sandbox
        result = await self.sandbox.execute(
            execution_id=execution_id,
            agent_type=agent_type,
            manifest=manifest,
            params=params,
            timeout=timeout,
            audit_id=audit_id
        )
        
        # Update statistics
        await self._update_stats(agent_type, result)
        
        return result
    
    async def queue_async(
        self,
        execution_id: str,
        agent_type: str,
        params: Dict[str, Any],
        callback_url: Optional[str],
        audit_id: str
    ):
        """Queue an agent for async execution."""
        await self._execution_queue.put({
            "execution_id": execution_id,
            "agent_type": agent_type,
            "params": params,
            "callback_url": callback_url,
            "audit_id": audit_id,
            "queued_at": datetime.utcnow().isoformat()
        })
        
        # Store initial status
        await self.redis.hset(f"exec:{execution_id}", mapping={
            "status": "queued",
            "agent_type": agent_type,
            "audit_id": audit_id
        })
    
    async def get_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get execution status."""
        data = await self.redis.hgetall(f"exec:{execution_id}")
        if not data:
            return None
        
        return {
            "execution_id": execution_id,
            "status": data.get("status"),
            "agent_type": data.get("agent_type"),
            "progress": int(data.get("progress", 0)),
            "result": json.loads(data.get("result", "null")) if data.get("result") else None
        }
    
    async def list_agents(self) -> List[Dict[str, Any]]:
        """List all available agents."""
        return await self.registry.list_agents()
    
    async def get_agent_schema(self, agent_type: str) -> Optional[Dict[str, Any]]:
        """Get agent input schema."""
        manifest = await self.registry.get_manifest(agent_type)
        if manifest:
            return manifest.get("schema", {})
        return None
    
    async def disable_agent(self, agent_type: str):
        """Disable an agent type."""
        await self.registry.set_enabled(agent_type, False)
    
    async def enable_agent(self, agent_type: str):
        """Enable an agent type."""
        await self.registry.set_enabled(agent_type, True)
    
    async def _worker_loop(self, worker_id: str):
        """Async worker loop for queue processing."""
        logger.info(f"Worker {worker_id} started")
        
        while self.running:
            try:
                # Get task from queue with timeout
                task = await asyncio.wait_for(
                    self._execution_queue.get(),
                    timeout=1.0
                )
                
                # Execute
                await self.execute(
                    execution_id=task["execution_id"],
                    agent_type=task["agent_type"],
                    params=task["params"],
                    timeout=300,  # 5 min for async
                    audit_id=task["audit_id"]
                )
                
                # Send callback if configured
                if task.get("callback_url"):
                    await self._send_callback(task["callback_url"], task)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
    
    async def _send_callback(self, url: str, task: Dict[str, Any]):
        """Send webhook callback."""
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=task) as resp:
                    logger.info(f"Callback to {url}: {resp.status}")
        except Exception as e:
            logger.error(f"Callback failed: {e}")
    
    async def _update_stats(self, agent_type: str, result: Dict[str, Any]):
        """Update execution statistics."""
        pipe = self.redis.pipeline()
        pipe.incr("stats:total_executions")
        pipe.incr(f"stats:agent:{agent_type}")
        await pipe.execute()
