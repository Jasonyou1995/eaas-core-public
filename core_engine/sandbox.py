import asyncio
import logging
import os
import json
import docker
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger("eaas.sandbox")

@dataclass
class SandboxConfig:
    """Security-hardened sandbox configuration."""
    
    # Resource limits
    memory_limit: str = "512m"
    cpu_limit: float = 0.5
    timeout_seconds: int = 30
    
    # Security settings
    user: str = "1000:1000"  # non-root
    read_only: bool = True
    no_new_privs: bool = True
    network_mode: str = "none"  # isolated by default
    
    # Whitelisted external APIs (if network needed)
    allowed_hosts: list = None
    
    def __post_init__(self):
        if self.allowed_hosts is None:
            self.allowed_hosts = []

class SandboxManager:
    """
    Docker-based sandbox for agent execution.
    
    Security features:
    - Non-root container execution
    - Read-only root filesystem
    - No new privileges
    - Optional network isolation
    - Resource quotas (CPU/memory)
    - Seccomp profiles
    """
    
    def __init__(self):
        self.docker_client = docker.from_env()
        self.container_prefix = "eaas-agent"
    
    async def execute(
        self,
        execution_id: str,
        agent_type: str,
        manifest: Dict[str, Any],
        params: Dict[str, Any],
        timeout: int,
        audit_id: str
    ) -> Dict[str, Any]:
        """
        Execute agent in isolated container.
        
        Returns execution result or raises exception on failure.
        """
        container_name = f"{self.container_prefix}-{execution_id[:8]}"
        config = self._build_config(manifest, timeout)
        
        # Prepare environment
        env = {
            "EAAS_EXECUTION_ID": execution_id,
            "EAAS_AGENT_TYPE": agent_type,
            "EAAS_PARAMS": json.dumps(params),
            "EAAS_AUDIT_ID": audit_id,
            "EAAS_TIMEOUT": str(timeout),
            "PYTHONUNBUFFERED": "1"
        }
        
        # Add scoped secrets from manifest
        if "env_vars" in manifest:
            for var_name in manifest["env_vars"]:
                if value := os.getenv(var_name):
                    env[var_name] = value
        
        try:
            # Run container
            container = self.docker_client.containers.run(
                image="eaas/agent-runner:latest",
                name=container_name,
                command=[
                    "python", "-m", "agent_runner",
                    "--agent-type", agent_type,
                    "--plugin-path", f"/app/plugins/{agent_type.replace('.', '/')}"
                ],
                environment=env,
                mem_limit=config.memory_limit,
                cpu_quota=int(config.cpu_limit * 100000),
                user=config.user,
                read_only=config.read_only,
                security_opt=[
                    "no-new-privileges:true",
                    f"seccomp={self._get_seccomp_profile()}"
                ],
                network_mode=config.network_mode if not config.allowed_hosts else "bridge",
                volumes=self._build_volumes(manifest),
                detach=True,
                auto_remove=False,  # We'll remove after collecting logs
                stdout=True,
                stderr=True
            )
            
            logger.info(f"Started container {container_name} for {agent_type}")
            
            # Wait for completion with timeout
            try:
                result = container.wait(timeout=timeout)
                exit_code = result.get("StatusCode", -1)
                
                # Collect output
                logs = container.logs(stdout=True, stderr=True).decode("utf-8")
                
                # Parse result from logs (last line should be JSON)
                output = self._parse_output(logs)
                
                if exit_code == 0:
                    return {
                        "status": "success",
                        "data": output,
                        "logs": logs[:1000] if os.getenv("DEBUG") else None
                    }
                else:
                    return {
                        "status": "error",
                        "error": output.get("error", "Unknown error"),
                        "exit_code": exit_code,
                        "logs": logs[:2000]
                    }
                    
            except Exception as e:
                logger.error(f"Container execution failed: {e}")
                container.kill()
                raise
                
        finally:
            # Cleanup
            try:
                container.remove(force=True)
            except:
                pass
    
    def _build_config(self, manifest: Dict[str, Any], timeout: int) -> SandboxConfig:
        """Build sandbox config from manifest."""
        resources = manifest.get("resources", {})
        permissions = manifest.get("permissions", {})
        network = permissions.get("network", [])
        
        return SandboxConfig(
            memory_limit=resources.get("memory", "512m"),
            cpu_limit=resources.get("cpu", 0.5),
            timeout_seconds=timeout,
            network_mode="bridge" if network else "none",
            allowed_hosts=network
        )
    
    def _build_volumes(self, manifest: Dict[str, Any]) -> Dict[str, Dict]:
        """Build volume mounts with restricted permissions."""
        volumes = {}
        
        # Read-only plugin code
        fs_perms = manifest.get("permissions", {}).get("filesystem", {})
        
        # Plugin directory (read-only)
        plugin_path = f"/app/plugins/{manifest['name']}"
        volumes[plugin_path] = {
            "bind": plugin_path,
            "mode": "ro"
        }
        
        # Writable temp directory (tmpfs)
        volumes["/tmp"] = {
            "bind": "/tmp",
            "mode": "rw"
        }
        
        # Optional data directories
        for path in fs_perms.get("read", []):
            volumes[path] = {"bind": path, "mode": "ro"}
        
        for path in fs_perms.get("write", []):
            volumes[path] = {"bind": path, "mode": "rw"}
        
        return volumes
    
    def _get_seccomp_profile(self) -> str:
        """Get path to seccomp profile."""
        profile_path = "/app/docker/security/agent-seccomp.json"
        if os.path.exists(profile_path):
            return profile_path
        return "default"
    
    def _parse_output(self, logs: str) -> Dict[str, Any]:
        """Parse JSON output from container logs."""
        lines = logs.strip().split("\n")
        
        # Try to parse last line as JSON result
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        
        return {"raw_output": logs}
    
    async def cleanup_all(self):
        """Clean up all running agent containers."""
        try:
            containers = self.docker_client.containers.list(
                filters={"name": self.container_prefix}
            )
            for container in containers:
                logger.info(f"Cleaning up container {container.name}")
                container.kill()
                container.remove(force=True)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
