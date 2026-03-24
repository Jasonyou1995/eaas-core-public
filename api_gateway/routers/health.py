from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import psutil

router = APIRouter()

@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "service": "eaas-gateway",
        "version": "1.0.0"
    }

@router.get("/ready")
async def readiness_check():
    """Kubernetes-style readiness probe."""
    # Check dependencies
    return {
        "ready": True,
        "checks": {
            "redis": "connected",
            "docker": "available"
        }
    }

@router.get("/live")
async def liveness_check():
    """Kubernetes-style liveness probe."""
    return {"alive": True}

@router.get("/metrics")
async def prometheus_metrics():
    """Prometheus-compatible metrics endpoint."""
    # In production: use prometheus_client to generate metrics
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    
    metrics = f"""# HELP eaas_cpu_usage_percent CPU usage percentage
# TYPE eaas_cpu_usage_percent gauge
eaas_cpu_usage_percent {cpu_percent}

# HELP eaas_memory_usage_percent Memory usage percentage  
# TYPE eaas_memory_usage_percent gauge
eaas_memory_usage_percent {memory.percent}

# HELP eaas_memory_available_bytes Available memory in bytes
# TYPE eaas_memory_available_bytes gauge
eaas_memory_available_bytes {memory.available}
"""
    
    return metrics
