# Urumi Enterprise MCP Platform
## WooCommerce Kubernetes Hosting Engine & Team Model Context Protocol (MCP) Gateway

[![Kubernetes](https://img.shields.io/badge/Kubernetes-v1.28%2B-blue?logo=kubernetes)](https://kubernetes.io/)
[![Helm](https://img.shields.io/badge/Helm-v3-0F1689?logo=helm)](https://helm.sh/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.3-61DAFB?logo=react)](https://react.dev/)
[![MCP](https://img.shields.io/badge/Protocol-MCP%20Streamable%20HTTP-8A2BE2)](https://modelcontextprotocol.io/)

Production-grade, high-availability Model Context Protocol (MCP) Gateway and Kubernetes Multi-Tenant WooCommerce Hosting Engine with zero-touch Day-0 bootstrapping, role-based tool governance (RBAC), and tamper-evident cryptographic audit logs.

---

## 🏛️ System Architecture

The platform implements the official [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) JSON-RPC 2.0 specifications over **Streamable HTTP** (`/mcp`):

```
                                  ┌──────────────────────────────────────────────┐
                                  │   Claude Code CLI / Cursor / React UI        │
                                  │      (MCP Clients with urumi_sk_* keys)      │
                                  └──────────────────────┬───────────────────────┘
                                                         │
                                                         ▼
                                  ┌──────────────────────────────────────────────┐
                                  │    High-Availability MCP Gateway & Engine    │
                                  │            (FastAPI Engine :8000)            │
                                  │                                              │
                                  │  - Sliding Token-Bucket Rate Limiter         │
                                  │  - Instant Key Revocation (urumi_sk_*)       │
                                  │  - SSRF Cloud Metadata Guard                 │
                                  │  - Circuit Breakers & Auto Health Probing    │
                                  │  - Collision Namespacing ({slug}__{fn})      │
                                  │  - Role-Based Tool RBAC (admin vs member)    │
                                  │  - Standout #4: Meta-Tool Scale Search Mode  │
                                  │  - Standout #5: Hosted MCP Container Engine  │
                                  │  - Bonus: Multi-Store K8s Tenant Controller  │
                                  │  - SHA-256 Tamper-Evident Chained Audit Log  │
                                  └──────┬──────────────┬──────────────┬─────────┘
                                         │              │              │
                   ┌─────────────────────┘              │              └──────────────────┐
                   ▼                                    ▼                                 ▼
   ┌──────────────────────────────┐    ┌─────────────────────────┐    ┌───────────────────────────────────┐
   │       woo-mcp (:8001)        │    │    promos-mcp (:8002)   │    │          ops-mcp (:8003)          │
   │ - woo__list_products         │    │ - promos__calculate...  │    │ - ops__send_order_summary_alert   │
   │ - woo__create_product        │    │ - promos__recommend...  │    │ - ops__list_dispatched_alerts     │
   │ - woo__list_orders           │    │ - promos__convert_cu... │    │ - ops__create_fulfillment_ticket  │
   │ - woo__get_order             │    └─────────────────────────┘    └───────────────────────────────────┘
   │ - woo__update_order_status   │
   └───────────────┬──────────────┘
                   │
                   ▼ (Bonus Dynamic Tenant Namespaces)
   ┌─────────────────────────────────────────────────────────────┐
   │ Kubernetes Isolated Tenant Namespaces: `urumi-store-{slug}`  │
   │  - ResourceQuota (2 CPU, 4Gi Mem) & LimitRange              │
   │  - Default-Deny NetworkPolicy (Only Ingress & Gateway Pod) │
   │  - MariaDB + PVC, WordPress + PVC, wp-cli Setup Job         │
   │  - Dedicated `woocommerce-mcp` Pod in tenant namespace      │
   │  - Auto-registered as `store_{slug}` in Gateway mesh        │
   └─────────────────────────────────────────────────────────────┘
```

---

## 📂 Monorepo Structure

```
urumi-mcp-platform/
├── charts/
│   ├── urumi-platform/            # Production & Local Platform Helm Chart
│   │   ├── Chart.yaml
│   │   ├── values.yaml            # Base values and resource defaults
│   │   ├── values-local.yaml      # Kind / k3d / Minikube configuration (*.127.0.0.1.nip.io)
│   │   ├── values-prod.yaml       # Production k3s VPS config (Traefik, cert-manager TLS)
│   │   └── templates/
│   │       ├── _helpers.tpl
│   │       ├── secrets.yaml
│   │       ├── rbac.yaml          # ServiceAccount & ClusterRole for tenant provisioning
│   │       ├── networkpolicies.yaml # Strict pod isolation & MCP ingress restrictions
│   │       ├── postgres.yaml      # Standout #7: PostgreSQL backing HA Gateway replicas
│   │       ├── mariadb-statefulset.yaml # WooCommerce database + PVC
│   │       ├── wordpress-deployment.yaml# WooCommerce storefront & admin
│   │       ├── wordpress-bootstrap-job.yaml # Zero-touch Day-0 wp-cli bootstrapping
│   │       ├── woocommerce-mcp-deployment.yaml
│   │       ├── promos-mcp-deployment.yaml
│   │       ├── ops-mcp-deployment.yaml
│   │       ├── gateway-deployment.yaml # HA Gateway (replicas: 2+)
│   │       ├── dashboard-deployment.yaml # React frontend dashboard
│   │       └── ingress.yaml       # L7 Ingress for Store, Gateway, and Dashboard
│   └── woo-store-tenant/          # Dynamic Multi-Store Tenant Chart
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/             # Quotas, NetworkPolicies, MariaDB, WP, and woo-mcp
├── dashboard/                     # React + TypeScript + Tailwind Enterprise Dashboard
│   ├── src/
│   │   ├── App.tsx                # App state, tabs & user switcher
│   │   ├── api.ts                 # Typed API client for Gateway & MCP protocol
│   │   ├── types.ts               # Complete TypeScript data models
│   │   └── components/
│   │       ├── Navbar.tsx         # 1-click User Switcher (Admin/Member) & MCP Endpoint
│   │       ├── ServersTab.tsx     # MCP Servers Mesh, Latency P95, Hosted Deploy Modal
│   │       ├── ChatTab.tsx        # Conversational AI with inline Tool Execution Pills
│   │       ├── StoresTab.tsx      # Bonus: Multi-Store tenant creation & quota meters
│   │       ├── TeamKeysTab.tsx    # Key generator, Cursor/Claude CLI snippets, RBAC matrix
│   │       └── AuditLogTab.tsx    # Tamper-Evident SHA-256 Audit Trail & Verify Badge
│   ├── nginx.conf                 # Hardened Nginx reverse proxy
│   └── Dockerfile                 # Multi-stage production container build
├── gateway-backend/               # High-Availability MCP Gateway Core
│   ├── app/
│   │   ├── main.py                # Gateway lifespan, auto-seeding, background health check
│   │   ├── mcp_gateway.py         # Streamable HTTP MCP engine, RBAC, tamper-evident audit
│   │   ├── upstream_manager.py    # Circuit breaker, 2.5s list timeout, 10s call timeout
│   │   ├── k8s_provisioner.py     # Bonus: Kubernetes Multi-Store & Hosted Container Engine
│   │   ├── meta_tools.py          # Standout #4: Meta-Tool Search Mode
│   │   ├── chat_agent.py          # Multi-server conversational agent with user context
│   │   └── routers/
│   │       ├── auth.py            # JWT authentication & user switching
│   │       ├── servers.py         # Standout #5: Hosted & External MCP Server Deployer
│   │       ├── stores.py          # Bonus: Multi-Store WooCommerce Tenant Provisioning
│   │       ├── keys.py            # urumi_sk API key generation & instant revocation
│   │       └── audit.py           # Immutable audit logs & cryptographic verification
│   └── Dockerfile
├── mcp-servers/                   # Streamable HTTP MCP Servers (Python 3.12, FastMCP)
│   ├── woocommerce-mcp/           # 5 WooCommerce v3 tools
│   ├── promos-analytics-mcp/      # 3 pure-compute analytics tools
│   └── ops-notifier-mcp/          # 3 alert & fulfillment ticketing tools
├── scripts/
│   ├── deploy-local.sh            # Automated Kind / k3d cluster creation & Helm rollout
│   ├── deploy-prod-k3s.sh         # Production k3s VPS deployment with cert-manager TLS
│   └── verify-dod.sh              # 100% automated Definition of Done verification test
├── SYSTEM_DESIGN.md               # Architecture tradeoffs and failure modes
├── THREAT_MODEL.md                # Analysis of the 4 mandatory security threat vectors
└── tests/
    ├── test_phase1_e2e.py         # Phase 1 verification test suite (8/8 passed)
    └── test_phase2_backend.py     # Phase 2 verification test suite (7/7 passed)
```

---

## ⚡ Quickstart

### 1. Automated Definition of Done Verification
To verify every requirement and Definition of Done item in one automated pass:

```bash
./scripts/verify-dod.sh
```
```
==> [DoD 1/8] Verifying Gateway Health Endpoint...
  ✓ Gateway /healthz responds 200 OK: {'status': 'ok'}
==> [DoD 2/8] Authenticating User A (Admin) and User B (Member)...
  ✓ User A (admin@urumi.local) authenticated successfully.
  ✓ User B (member@urumi.local) authenticated successfully.
==> [DoD 3/8] User A: Create Product via Chat Agent...
  ✓ Tool Trace: ['woo__create_product']
==> [DoD 4/8] User A: Query Orders via Chat Agent...
  ✓ Orders Query Trace: ['woo__list_orders']
==> [DoD 5/8] User B: External MCP Client Protocol & RBAC Validation...
  ✓ Generated API key for User B: urumi_sk_...
  ✓ Confirmed: Restricted mutation tool 'woo__create_product' hidden from Member tools/list.
  ✓ Confirmed: Direct execution of 'woo__create_product' by Member rejected with REJECTED_FORBIDDEN.
==> [DoD 6/8] Instant API Key Revocation...
  ✓ Confirmed: Post-revocation call rejected immediately with HTTP 401 Unauthorized.
==> [DoD 7/8] Upstream Server Disable & Tool Pruning...
  ✓ Confirmed: 'promos__*' tools immediately disappeared from tools/list.
==> [DoD 8/8] Tamper-Evident SHA-256 Audit Trail Verification...
  ✓ Confirmed: All audit records cryptographically verified with zero tampering!
🎉 ALL DEFINITION OF DONE (DoD) SCENARIOS FULLY VERIFIED WITH 100% SUCCESS!
```

---

## ☸️ Kubernetes Deployment Guide

### Option A: Local Kubernetes Deployment (Kind / k3d / Minikube)

Run the automated one-command script:
```bash
./scripts/deploy-local.sh
```
This script automatically:
1. Provisions a local `k3d` or `kind` cluster with extra port mappings (80/443).
2. Builds all 5 container images and imports them into the cluster.
3. Deploys the `urumi` Helm release with [`charts/urumi-platform/values-local.yaml`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/charts/urumi-platform/values-local.yaml).
4. Executes the Day-0 WooCommerce bootstrap job.

**Local Access Endpoints (`*.127.0.0.1.nip.io`):**
- **Dashboard UI**: `http://app.127.0.0.1.nip.io`
- **MCP Gateway Endpoint**: `http://gateway.127.0.0.1.nip.io/mcp`
- **WooCommerce Storefront**: `http://store.127.0.0.1.nip.io`
- **WordPress Admin**: `http://store.127.0.0.1.nip.io/wp-admin` (`admin` / `UrumiWooPass2026!`)

---

### Option B: Production VPS Deployment (k3s + Traefik + cert-manager)

Target a Linux VPS running k3s:
```bash
DOMAIN="urumi.yourdomain.com" ./scripts/deploy-prod-k3s.sh
```
Or use the VPS Public IP directly:
```bash
VPS_IP="198.51.100.25" ./scripts/deploy-prod-k3s.sh
```
This deploys with [`charts/urumi-platform/values-prod.yaml`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/charts/urumi-platform/values-prod.yaml):
- Automated Let's Encrypt TLS certificates managed by `cert-manager`.
- Zero plaintext secrets in Git (secrets injected at runtime into `urumi-prod-secrets`).
- Production high-availability Gateway (3 replicas) backed by PostgreSQL.

---

## 🔄 Helm Lifecycle: Upgrades, History & Rollbacks

### 1. Upgrade the Platform Configuration
```bash
# Scale Gateway to 4 replicas and update limits
helm upgrade urumi ./charts/urumi-platform \
  -n urumi \
  -f ./charts/urumi-platform/values-local.yaml \
  --set gateway.replicaCount=4 \
  --wait
```

### 2. View Release History
```bash
helm history urumi -n urumi
```
Output:
```
REVISION  UPDATED                   STATUS      CHART                 APP VERSION  DESCRIPTION
1         Sat Oct 17 00:00:00 2026  SUPERSEDED  urumi-platform-1.0.0  1.0.0        Install complete
2         Sat Oct 17 00:15:00 2026  DEPLOYED    urumi-platform-1.0.0  1.0.0        Upgrade complete
```

### 3. Instant Safe Rollback
```bash
# Rollback immediately to Revision 1 if an issue occurs
helm rollback urumi 1 -n urumi --wait
```

---

## 🛒 Placing a Test Order via Cash on Delivery (COD)

Day-0 zero-touch bootstrapping enables COD out-of-the-box. To place an order:
1. Open the Storefront at `http://store.127.0.0.1.nip.io`.
2. Click on **"Urumi Kubernetes Hoodie"** ($49.99) -> **"Add to Cart"** -> **"Proceed to Checkout"**.
3. Fill in test customer billing details (Name: `Alex Developer`, Address: `100 Cluster Way`).
4. Select **"Cash on Delivery"** -> Click **"Place Order"**.
5. Instantly, open the Dashboard **Chat Agent** tab and type:
   > *"What orders came in today on the WooCommerce store?"*
   The Chat Agent invokes `woo__list_orders` under your identity and displays the newly placed order with live execution duration and parameters.

---

## 🔌 Connecting Claude Code, Cursor & MCP Clients

### 1. Generate Personal API Key
1. Navigate to the **"Team & Keys"** tab in the Dashboard.
2. Click **"Generate New API Key"**, label it (e.g., `MacBook Cursor`), and copy the raw key: `urumi_sk_...`.

### 2. Cursor IDE Integration (`.cursor/mcp.json`)
Create or edit `.cursor/mcp.json` in your repository:
```json
{
  "mcpServers": {
    "urumi-gateway": {
      "url": "http://gateway.127.0.0.1.nip.io/mcp",
      "headers": {
        "Authorization": "Bearer urumi_sk_YOUR_RAW_KEY_HERE"
      }
    }
  }
}
```

### 3. Claude Code CLI Integration
Run the Claude Code CLI add command:
```bash
claude mcp add --transport http urumi-gateway http://gateway.127.0.0.1.nip.io/mcp --header "Authorization: Bearer urumi_sk_YOUR_RAW_KEY_HERE"
```

### 4. Official MCP Inspector
```bash
npx @modelcontextprotocol/inspector http://gateway.127.0.0.1.nip.io/mcp
```
Pass header: `Authorization: Bearer urumi_sk_...`.

---

## 🏆 Bonus & Standout Implementations Index

| Feature | Category | Exact Implementation File(s) |
| :--- | :--- | :--- |
| **Multi-Store Kubernetes Provisioning** | **Bonus** | [`gateway-backend/app/k8s_provisioner.py`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/gateway-backend/app/k8s_provisioner.py), [`routers/stores.py`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/gateway-backend/app/routers/stores.py), [`charts/woo-store-tenant/`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/charts/woo-store-tenant/) |
| **Tamper-Evident SHA-256 Audit Trail** | **Bonus** | [`gateway-backend/app/mcp_gateway.py`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/gateway-backend/app/mcp_gateway.py), [`routers/audit.py`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/gateway-backend/app/routers/audit.py), [`dashboard/src/components/AuditLogTab.tsx`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/dashboard/src/components/AuditLogTab.tsx) |
| **Meta-Tool Search Mode (`gateway__search_tools`)**| **Standout #4** | [`gateway-backend/app/meta_tools.py`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/gateway-backend/app/meta_tools.py), [`dashboard/src/components/ServersTab.tsx`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/dashboard/src/components/ServersTab.tsx) |
| **Hosted MCP Server Deployer by Container Image** | **Standout #5** | [`gateway-backend/app/routers/servers.py`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/gateway-backend/app/routers/servers.py), [`k8s_provisioner.py`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/gateway-backend/app/k8s_provisioner.py) |
| **High-Availability Gateway Engine (Multi-Pod)** | **Standout #7** | [`charts/urumi-platform/templates/gateway-deployment.yaml`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/charts/urumi-platform/templates/gateway-deployment.yaml), [`templates/postgres.yaml`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/charts/urumi-platform/templates/postgres.yaml) |
| **Zero-Touch Day-0 WooCommerce Bootstrap Job** | **Core Requirement** | [`charts/urumi-platform/templates/wordpress-bootstrap-job.yaml`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/charts/urumi-platform/templates/wordpress-bootstrap-job.yaml) |
| **Enterprise Dark-Mode React Dashboard** | **Core Requirement** | [`dashboard/`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/dashboard/) (Navbar, ServersTab, ChatTab, StoresTab, TeamKeysTab, AuditLogTab) |

---

## 🔒 Security & System Design Documentation

- Detailed Architecture & Design Choices: [`SYSTEM_DESIGN.md`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/SYSTEM_DESIGN.md)
- Complete Threat Model & Risk Analysis: [`THREAT_MODEL.md`](file:///home/harshit/Desktop/Internship%20Assisment/Urumi/urumi-mcp-platform/THREAT_MODEL.md)
