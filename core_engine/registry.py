import os
import yaml
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger("eaas.registry")

class PluginRegistry:
    """
    Plugin discovery and manifest management.
    
    Scans directories for agent plugins and maintains manifest registry.
    """
    
    def __init__(self):
        self.manifests: Dict[str, Dict[str, Any]] = {}
        self.enabled: Dict[str, bool] = {}
    
    async def discover_plugins(self, plugin_dirs: List[str]):
        """
        Discover plugins in specified directories.
        
        Each plugin must have an eaas.yaml manifest file.
        """
        logger.info(f"Discovering plugins in: {plugin_dirs}")
        
        for directory in plugin_dirs:
            if not os.path.exists(directory):
                logger.warning(f"Plugin directory not found: {directory}")
                continue
            
            await self._scan_directory(directory)
        
        logger.info(f"Discovered {len(self.manifests)} plugins")
    
    async def _scan_directory(self, directory: str):
        """Scan a directory for plugin manifests."""
        for root, dirs, files in os.walk(directory):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            
            if "eaas.yaml" in files:
                manifest_path = Path(root) / "eaas.yaml"
                try:
                    manifest = self._load_manifest(manifest_path)
                    agent_type = manifest.get("name")
                    
                    if agent_type:
                        self.manifests[agent_type] = manifest
                        self.enabled[agent_type] = True
                        logger.info(f"Registered plugin: {agent_type}")
                        
                except Exception as e:
                    logger.error(f"Failed to load manifest {manifest_path}: {e}")
    
    def _load_manifest(self, path: Path) -> Dict[str, Any]:
        """Load and validate manifest file."""
        with open(path, "r") as f:
            manifest = yaml.safe_load(f)
        
        # Validate required fields
        required = ["name", "version"]
        for field in required:
            if field not in manifest:
                raise ValueError(f"Missing required field: {field}")
        
        # Set defaults
        manifest.setdefault("permissions", {})
        manifest.setdefault("resources", {})
        manifest.setdefault("resources", {}).setdefault("memory", "512m")
        manifest.setdefault("resources", {}).setdefault("cpu", 0.5)
        manifest.setdefault("resources", {}).setdefault("timeout", 30)
        
        return manifest
    
    async def get_manifest(self, agent_type: str) -> Optional[Dict[str, Any]]:
        """Get manifest for agent type."""
        if not self.enabled.get(agent_type, False):
            return None
        return self.manifests.get(agent_type)
    
    async def list_agents(self) -> List[Dict[str, Any]]:
        """List all registered agents with metadata."""
        agents = []
        
        for agent_type, manifest in self.manifests.items():
            if self.enabled.get(agent_type, False):
                agents.append({
                    "type": agent_type,
                    "name": manifest.get("name"),
                    "version": manifest.get("version"),
                    "author": manifest.get("author", "Unknown"),
                    "description": manifest.get("description", ""),
                    "enabled": True
                })
        
        return agents
    
    async def set_enabled(self, agent_type: str, enabled: bool):
        """Enable or disable an agent type."""
        if agent_type in self.manifests:
            self.enabled[agent_type] = enabled
            action = "enabled" if enabled else "disabled"
            logger.info(f"Plugin {agent_type} {action}")
    
    def get_agent_path(self, agent_type: str) -> Optional[str]:
        """Get filesystem path for agent plugin."""
        # Convert agent.type to path agent/type
        relative_path = agent_type.replace(".", "/")
        
        # Search in plugin directories
        for base_dir in ["/app/sample_plugins", "/app/private"]:
            full_path = os.path.join(base_dir, relative_path)
            if os.path.exists(full_path):
                return full_path
        
        return None
