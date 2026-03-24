import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger("eaas.permissions")

@dataclass
class Policy:
    """Permission policy for API key."""
    api_key_prefix: str
    allowed_agents: List[str]
    max_executions_per_minute: int
    max_concurrent: int
    allowed_params: Dict[str, List[str]]

class PermissionEngine:
    """
    Role-based access control and policy enforcement.
    
    Manages:
    - API key validation
    - Agent access control
    - Parameter sanitization
    - Rate limiting by tier
    """
    
    def __init__(self, redis):
        self.redis = redis
        self.policies: Dict[str, Policy] = {}
        self._load_default_policies()
    
    def _load_default_policies(self):
        """Load default permission policies."""
        # Free tier
        self.policies["ek_free"] = Policy(
            api_key_prefix="ek_free",
            allowed_agents=["sample.*"],
            max_executions_per_minute=100,
            max_concurrent=2,
            allowed_params={"*": []}  # All params allowed for sample agents
        )
        
        # Pro tier
        self.policies["ek_pro"] = Policy(
            api_key_prefix="ek_pro",
            allowed_agents=["sample.*", "premium.*"],
            max_executions_per_minute=1000,
            max_concurrent=10,
            allowed_params={"*": []}
        )
        
        # Enterprise tier
        self.policies["ek_ent"] = Policy(
            api_key_prefix="ek_ent",
            allowed_agents=["*"],  # All agents including private
            max_executions_per_minute=10000,
            max_concurrent=100,
            allowed_params={"*": []}
        )
    
    async def validate_agent_access(self, api_key: str, agent_type: str):
        """
        Validate API key has permission to execute agent.
        
        Raises PermissionError if not authorized.
        """
        policy = self._get_policy(api_key)
        
        if not policy:
            raise PermissionError("Invalid API key")
        
        # Check if agent type is allowed
        allowed = any(
            self._match_pattern(agent_type, pattern)
            for pattern in policy.allowed_agents
        )
        
        if not allowed:
            raise PermissionError(
                f"API key not authorized for agent: {agent_type}"
            )
        
        # Check concurrent execution limit
        current = await self._get_concurrent_count(api_key)
        if current >= policy.max_concurrent:
            raise PermissionError(
                f"Concurrent execution limit reached ({policy.max_concurrent})"
            )
        
        logger.info(f"Access granted: {api_key[:8]}... -> {agent_type}")
    
    def _get_policy(self, api_key: str) -> Optional[Policy]:
        """Get policy for API key."""
        for prefix, policy in self.policies.items():
            if api_key.startswith(prefix):
                return policy
        return None
    
    def _match_pattern(self, value: str, pattern: str) -> bool:
        """Match value against wildcard pattern."""
        import fnmatch
        return fnmatch.fnmatch(value, pattern)
    
    async def _get_concurrent_count(self, api_key: str) -> int:
        """Get current concurrent execution count for API key."""
        count = await self.redis.get(f"concurrent:{api_key[:16]}")
        return int(count) if count else 0
    
    async def increment_concurrent(self, api_key: str):
        """Increment concurrent execution counter."""
        await self.redis.incr(f"concurrent:{api_key[:16]}")
        await self.redis.expire(f"concurrent:{api_key[:16]}", 300)  # 5 min TTL
    
    async def decrement_concurrent(self, api_key: str):
        """Decrement concurrent execution counter."""
        await self.redis.decr(f"concurrent:{api_key[:16]}")
    
    async def sanitize_params(
        self,
        api_key: str,
        agent_type: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Sanitize and validate parameters.
        
        Removes disallowed parameters and validates types.
        """
        policy = self._get_policy(api_key)
        if not policy:
            return params
        
        allowed = policy.allowed_params.get(agent_type, [])
        wildcard_allowed = policy.allowed_params.get("*", [])
        
        # If no restrictions specified, allow all
        if not allowed and not wildcard_allowed:
            return params
        
        # Filter to allowed params
        sanitized = {}
        for key, value in params.items():
            if key in allowed or key in wildcard_allowed:
                # Basic type validation
                if self._is_safe_value(value):
                    sanitized[key] = value
                else:
                    logger.warning(f"Blocked unsafe value for {key}")
            else:
                logger.warning(f"Blocked disallowed param: {key}")
        
        return sanitized
    
    def _is_safe_value(self, value: Any) -> bool:
        """Check if parameter value is safe."""
        if isinstance(value, (str, int, float, bool)):
            # Block dangerous strings
            if isinstance(value, str):
                dangerous = [";", "|", "`", "$", "\n", "\r"]
                return not any(d in value for d in dangerous)
            return True
        elif isinstance(value, (list, dict)):
            # Recursively check collections
            if isinstance(value, dict):
                return all(
                    self._is_safe_value(k) and self._is_safe_value(v)
                    for k, v in value.items()
                )
            return all(self._is_safe_value(v) for v in value)
        return False
