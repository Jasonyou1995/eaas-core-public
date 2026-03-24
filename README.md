# EaaS Core — Enterprise Agent-as-a-Service Framework

> **Execution-as-a-Service for Autonomous DeFi Agents**  
> Secure. Scalable. Compliant.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-green.svg)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)

---

## 🎯 What is EaaS?

**Execution-as-a-Service (EaaS)** is a secure containerized framework for deploying autonomous AI agents in regulated financial environments. It provides:

- **Strict Permission Boundaries**: Agents run as non-root in isolated containers with scoped API keys
- **Pluggable Architecture**: Private alpha strategies plug into the open-source core
- **Compliance-First Design**: Built-in audit trails, rate limiting, and risk controls
- **Enterprise Grade**: Horizontal scaling, health checks, and production monitoring

---

## 🏛️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                                     │
│  (Trading Desks, Institutional APIs, Retail Front-ends)                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      API GATEWAY (FastAPI)                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │  Auth       │  │  Rate Limit │  │  Validation │  │  Audit Logger   │ │
│  │  (JWT/API)  │  │  (Redis)    │  │  (Pydantic) │  │  (Immutable)    │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
┌───────────────────────┐ ┌───────────────┐ ┌─────────────────┐
│    CORE ENGINE        │ │  PLUGIN MGR   │ │  SECRET VAULT   │
│  (Agent Orchestrator) │ │  (Hot-swap)   │ │  (HashiCorp)    │
└───────────────────────┘ └───────────────┘ └─────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      PLUGIN EXECUTION CONTAINERS                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │  Sample Plugins │  │  PRIVATE PLUGINS │  │  (Submodule/Volume)     │  │
│  │  (This Repo)    │  │  (eaas-plugins-  │  │  Quant Strategies,      │  │
│  │                 │  │   private)       │  │  Compliance Oracles,    │  │
│  │  • Price Feed   │  │                  │  │  Billing Logic          │  │
│  │  • Risk Check   │  │  Mounted at      │  │                         │  │
│  │  • Notification │  │  /app/private    │  │  **Your Alpha Here**    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- Docker 24.0+
- Docker Compose 2.20+
- Python 3.11+ (for local dev)

### 1. Clone & Launch

```bash
git clone https://github.com/Jasonyou1995/eaas-core-public.git
cd eaas-core-public

# Copy environment template
cp .env.example .env

# Launch full stack
docker-compose up -d
```

### 2. Verify Installation

```bash
# Health check
curl http://localhost:8080/health

# Test agent execution
curl -X POST http://localhost:8080/v1/agents/execute \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "sample.price_feed",
    "params": {"symbol": "BTC-USD"}
  }'
```

---

## 📁 Repository Structure

```
eaas-core-public/
├── api_gateway/           # FastAPI public endpoints
│   ├── main.py           # Application entry
│   ├── routers/          # Route definitions
│   ├── middleware/       # Auth, rate limiting, audit
│   └── schemas/          # Pydantic models
├── core_engine/          # Agent orchestration logic
│   ├── orchestrator.py   # Agent lifecycle manager
│   ├── sandbox.py        # Container isolation
│   ├── permissions.py    # RBAC & policy engine
│   └── registry.py       # Plugin discovery
├── docker/               # Container configurations
│   ├── Dockerfile        # Hardened Python image
│   ├── docker-compose.yml
│   └── security/         # Seccomp, AppArmor profiles
├── sample_plugins/       # Reference implementations
│   ├── price_feed/       # Market data fetcher
│   ├── risk_guard/       # Pre-trade risk checks
│   └── notifier/         # Alert dispatcher
├── docs/                 # Architecture & API docs
└── tests/                # Integration & unit tests
```

---

## 🔐 Security Model

### Permission Boundaries

| Layer | User | Capabilities | Network |
|-------|------|--------------|---------|
| **API Gateway** | `eaas-gateway` | Read configs, route requests | Internal only |
| **Core Engine** | `eaas-engine` | Spawn containers, manage state | Internal only |
| **Agent Container** | `eaas-agent` (UID 1000) | Execute plugin code only | Whitelisted egress |
| **Private Plugins** | `eaas-plugin` (UID 1001) | Access scoped secrets | Wallet APIs only |

### Key Security Features

- **Non-root Execution**: All containers run as unprivileged users
- **Seccomp Profiles**: System call filtering per container role
- **Network Isolation**: Agents have no direct external access
- **Secret Injection**: API keys mounted as tmpfs, never in images
- **Immutable Audit**: All actions logged to append-only storage

---

## 🔌 Plugin Development

### Creating a Sample Plugin

```python
# sample_plugins/my_plugin/agent.py
from eaas_core import BaseAgent, AgentContext

class MyAgent(BaseAgent):
    name = "my_agent"
    version = "1.0.0"
    
    async def execute(self, ctx: AgentContext) -> dict:
        """Main execution entrypoint."""
        symbol = ctx.params.get("symbol")
        
        # Your logic here
        result = await self.fetch_data(symbol)
        
        return {
            "status": "success",
            "data": result,
            "audit_trail": ctx.audit_id
        }
```

### Plugin Manifest

```yaml
# sample_plugins/my_plugin/eaas.yaml
name: my_agent
version: 1.0.0
author: Your Name
permissions:
  network:
    - https://api.exchange.com
  filesystem:
    read: [/app/data]
    write: []
  env_vars:
    - EXTERNAL_API_KEY
resources:
  memory: 512m
  cpu: 0.5
  timeout: 30s
```

---

## 🏢 Enterprise Deployment

### Production Docker Compose

```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  gateway:
    build:
      context: .
      dockerfile: docker/Dockerfile
      target: gateway
    user: "1000:1000"
    read_only: true
    security_opt:
      - no-new-privileges:true
      - seccomp:docker/security/gateway-seccomp.json
    environment:
      - VAULT_ADDR=${VAULT_ADDR}
      - REDIS_URL=redis://redis:6379
    volumes:
      - type: tmpfs
        target: /tmp
        tmpfs:
          size: 100M
          noexec: true
    networks:
      - eaas-internal
    depends_on:
      - redis
      - vault
```

### Private Plugin Integration

Your proprietary strategies live in `eaas-plugins-private` and mount into the core:

```yaml
# In docker-compose.yml
services:
  agent-runner:
    volumes:
      - ../eaas-plugins-private:/app/private:ro
    environment:
      - PLUGIN_PATH=/app/private
      - STRATEGY_MODE=production
```

---

## 📊 Monitoring & Observability

```bash
# View agent execution logs
docker logs eaas-agent-runner -f

# Check audit trail
curl http://localhost:8080/v1/admin/audit \
  -H "Authorization: Bearer ADMIN_TOKEN"

# Prometheus metrics
curl http://localhost:8080/metrics
```

---

## 🛠️ Two-Repo System

This repository is **Repo A — The Framework**.

**Repo B — Your Alpha** (`eaas-plugins-private`):
- Proprietary trading strategies
- Compliance oracle integrations
- Billing and monetization logic
- Live API keys and secrets

**Connection Pattern:**
```
eaas-plugins-private/       eaas-core-public/
├── private_gateway/  ───►  ├── api_gateway/
├── cross_chain_arb/   ───►  ├── core_engine/
├── monetization/      ───►  └── docker/
└── secrets/
    └── Mounts as /app/private in production
```

---

## 📜 License

MIT License — See [LICENSE](LICENSE)

**Commercial Use**: The core framework is open source. Your proprietary plugins remain yours.

---

## 🤝 Contributing

We welcome contributions to the core framework. For security issues, please email security@eaas.dev

---

## 📬 Contact

- **Email**: jy98105@gmail.com

---

<p align="center">
  <em>Built for the future of autonomous finance.</em><br>
  <strong>Secure by design. Open by choice. Private where it matters.</strong>
</p>
