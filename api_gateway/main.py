from fastapi import FastAPI, Depends, HTTPException, Security, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import redis.asyncio as redis
import logging
import os

from api_gateway.routers import agents, admin, health, webhooks
from api_gateway.middleware.audit import AuditMiddleware
from api_gateway.middleware.rate_limit import RateLimitMiddleware
from core_engine.orchestrator import AgentOrchestrator
from core_engine.permissions import PermissionEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("eaas.gateway")

# Security
security = HTTPBearer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting EaaS API Gateway...")
    
    # Initialize Redis
    app.state.redis = await redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379"),
        encoding="utf-8",
        decode_responses=True
    )
    
    # Initialize core components
    app.state.orchestrator = AgentOrchestrator(redis=app.state.redis)
    app.state.permissions = PermissionEngine(redis=app.state.redis)
    
    await app.state.orchestrator.initialize()
    logger.info("EaaS Gateway initialized successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down EaaS Gateway...")
    await app.state.redis.close()
    await app.state.orchestrator.shutdown()

# Create FastAPI app
app = FastAPI(
    title="EaaS — Execution-as-a-Service",
    description="Enterprise Agent Platform for Autonomous DeFi Operations",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if os.getenv("ENV") != "production" else None,
    redoc_url="/redoc" if os.getenv("ENV") != "production" else None,
)

# Middleware (order matters - executed bottom to top on request)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
app.add_middleware(AuditMiddleware)
app.add_middleware(RateLimitMiddleware, redis_url=os.getenv("REDIS_URL"))

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(
    agents.router,
    prefix="/v1/agents",
    tags=["Agents"],
    dependencies=[Depends(verify_api_key)]
)
app.include_router(
    admin.router,
    prefix="/v1/admin",
    tags=["Admin"],
    dependencies=[Depends(verify_admin_key)]
)
app.include_router(webhooks.router, prefix="/v1/webhooks", tags=["Webhooks"])

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verify API key and return scopes."""
    token = credentials.credentials
    # In production: validate against Vault or database
    if not token.startswith("ek_"):
        raise HTTPException(status_code=401, detail="Invalid API key format")
    return {"api_key": token, "scopes": ["agent:execute", "agent:read"]}

async def verify_admin_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verify admin API key."""
    token = credentials.credentials
    if not token.startswith("ek_admin_"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"api_key": token, "scopes": ["admin:*"]}

@app.get("/")
async def root():
    return {
        "service": "EaaS — Execution-as-a-Service",
        "version": "1.0.0",
        "status": "operational",
        "documentation": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api_gateway.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        workers=int(os.getenv("WORKERS", 1)),
        log_level="info"
    )
