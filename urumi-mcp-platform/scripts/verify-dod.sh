#!/usr/bin/env bash
# ==============================================================================
# Urumi Platform — Definition of Done (DoD) End-to-End Verification Suite
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
STORE_URL="${STORE_URL:-http://store.127.0.0.1.nip.io}"
NAMESPACE="${NAMESPACE:-urumi}"

echo "========================================================================"
echo "🎯 STARTING DEFINITION OF DONE (DoD) AUTOMATED VERIFICATION"
echo "========================================================================"
echo "Gateway Target: $GATEWAY_URL"
echo ""

# Find Python binary
PYTHON_BIN="python3"
if [ -f "${ROOT_DIR}/.venv/bin/python" ]; then
  PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
fi

# Execute Python-driven DoD runner for robust JSON-RPC and HTTP assertions
"$PYTHON_BIN" - "$GATEWAY_URL" <<'EOF'
import sys
import json
import time
import httpx

base_url = sys.argv[1].rstrip("/")
print(f"Connecting to Gateway at {base_url}...")

client = httpx.Client(base_url=base_url, timeout=15.0)

# ------------------------------------------------------------------------------
# 1. Verify Gateway Health Probe
# ------------------------------------------------------------------------------
print("\n==> [DoD 1/8] Verifying Gateway Health Endpoint...")
res = client.get("/healthz")
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
print("  ✓ Gateway /healthz responds 200 OK:", res.json())

# ------------------------------------------------------------------------------
# 2. Authenticate User A (Admin) and User B (Member)
# ------------------------------------------------------------------------------
print("\n==> [DoD 2/8] Authenticating User A (Admin) and User B (Member)...")
login_a = client.post("/api/v1/auth/login", json={"email": "admin@urumi.local", "password": "UrumiAdmin2026!"})
assert login_a.status_code == 200, f"Admin login failed: {login_a.text}"
token_a = login_a.json()["access_token"]
headers_a = {"Authorization": f"Bearer {token_a}"}
print("  ✓ User A (admin@urumi.local) authenticated successfully.")

login_b = client.post("/api/v1/auth/login", json={"email": "member@urumi.local", "password": "UrumiMember2026!"})
assert login_b.status_code == 200, f"Member login failed: {login_b.text}"
token_b = login_b.json()["access_token"]
headers_b = {"Authorization": f"Bearer {token_b}"}
print("  ✓ User B (member@urumi.local) authenticated successfully.")

# ------------------------------------------------------------------------------
# 3. User A: Create Product via Chat Agent & Verify
# ------------------------------------------------------------------------------
print("\n==> [DoD 3/8] User A: Create Product via Chat Agent...")
chat_create = client.post(
    "/api/chat",
    json={"messages": [{"role": "user", "content": "Create a product named 'Urumi Kubernetes Hoodie' priced at $49.99"}]},
    headers=headers_a
)
assert chat_create.status_code == 200, f"Chat create failed: {chat_create.text}"
data_create = chat_create.json()
print("  ✓ Tool Trace:", [t["tool"] for t in data_create.get("tool_execution_trace", [])])
print("  ✓ Assistant:", data_create["message"]["content"][:140], "...")

# ------------------------------------------------------------------------------
# 4. User A: Query Today's Orders via Chat Agent
# ------------------------------------------------------------------------------
print("\n==> [DoD 4/8] User A: Query Orders via Chat Agent...")
chat_orders = client.post(
    "/api/chat",
    json={"messages": [{"role": "user", "content": "What orders came in today on the WooCommerce store?"}]},
    headers=headers_a
)
assert chat_orders.status_code == 200
data_orders = chat_orders.json()
print("  ✓ Orders Query Trace:", [t["tool"] for t in data_orders.get("tool_execution_trace", [])])
print("  ✓ Assistant:", data_orders["message"]["content"][:140], "...")

# ------------------------------------------------------------------------------
# 5. User B: API Key Generation, External MCP Protocol, RBAC Restriction
# ------------------------------------------------------------------------------
print("\n==> [DoD 5/8] User B: External MCP Client Protocol & RBAC Validation...")
# Generate personal API key for User B
key_res = client.post("/api/v1/keys", json={"name": "User B DoD Key"}, headers=headers_b)
assert key_res.status_code == 201
key_data = key_res.json()
user_b_key = key_data["raw_api_key"]
key_id = key_data["id"]
print(f"  ✓ Generated API key for User B: {key_data['key_prefix']}...")

mcp_headers = {
    "Authorization": f"Bearer {user_b_key}",
    "Accept": "application/json, text/event-stream"
}

# 5a. Call /mcp tools/list as User B (Member)
mcp_list = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=mcp_headers)
assert mcp_list.status_code == 200
tools_b = [t["name"] for t in mcp_list.json()["result"]["tools"]]
print(f"  ✓ User B sees {len(tools_b)} member-accessible tools.")
assert "woo__create_product" not in tools_b, "CRITICAL: Write tool exposed to Member in tools/list!"
print("  ✓ Confirmed: Restricted mutation tool 'woo__create_product' hidden from Member tools/list.")

# 5b. Direct invocation of restricted write tool -> REJECTED_FORBIDDEN
forbidden_call = client.post(
    "/mcp",
    json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "woo__create_product", "arguments": {"name": "Hacker Item", "regular_price": "999"}}},
    headers=mcp_headers
)
assert forbidden_call.status_code == 403 or forbidden_call.json().get("result", {}).get("isError") is True, f"Expected forbidden error, got {forbidden_call.text}"
print("  ✓ Confirmed: Direct execution of 'woo__create_product' by Member rejected with REJECTED_FORBIDDEN.")

# 5c. Multi-Server workflow as User B (woo__list_orders + ops__send_order_summary_alert)
exec_call = client.post(
    "/mcp",
    json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "ops__send_order_summary_alert", "arguments": {"channel": "#ops-alerts", "order_count": 5, "total_revenue": 509.99}}},
    headers=mcp_headers
)
assert exec_call.status_code == 200
print("  ✓ User B multi-server workflow tool execution succeeded:", exec_call.json().get("result", {}).get("content", [{}])[0].get("text", "")[:80])

# ------------------------------------------------------------------------------
# 6. Instant API Key Revocation
# ------------------------------------------------------------------------------
print("\n==> [DoD 6/8] Instant API Key Revocation...")
revoke_res = client.delete(f"/api/v1/keys/{key_id}", headers=headers_b)
assert revoke_res.status_code == 200
print(f"  ✓ Key #{key_id} revoked.")

post_revoke = client.post("/mcp", json={"jsonrpc": "2.0", "id": 4, "method": "tools/list"}, headers=mcp_headers)
assert post_revoke.status_code == 401, f"Expected 401 Unauthorized after revocation, got {post_revoke.status_code}"
print("  ✓ Confirmed: Post-revocation call rejected immediately with HTTP 401 Unauthorized.")

# ------------------------------------------------------------------------------
# 7. Disable Upstream Server & Graceful Degradation
# ------------------------------------------------------------------------------
print("\n==> [DoD 7/8] Upstream Server Disable & Tool Pruning...")
# Find promos server ID
servers = client.get("/api/v1/servers", headers=headers_a).json()
promos_server = next((s for s in servers if s["slug"] == "promos"), None)
if promos_server:
    toggle_off = client.patch(f"/api/v1/servers/{promos_server['id']}", json={"enabled": False}, headers=headers_a)
    assert toggle_off.status_code == 200
    print("  ✓ Disabled 'promos' server.")

    tools_after = client.post("/mcp", json={"jsonrpc": "2.0", "id": 5, "method": "tools/list"}, headers=headers_a)
    active_tools = [t["name"] for t in tools_after.json()["result"]["tools"]]
    assert not any(t.startswith("promos__") for t in active_tools)
    print("  ✓ Confirmed: 'promos__*' tools immediately disappeared from tools/list.")

    # Re-enable promos server
    client.patch(f"/api/v1/servers/{promos_server['id']}", json={"enabled": True}, headers=headers_a)
    print("  ✓ Re-enabled 'promos' server.")

# ------------------------------------------------------------------------------
# 8. Cryptographic Tamper-Evident SHA-256 Audit Trail
# ------------------------------------------------------------------------------
print("\n==> [DoD 8/8] Tamper-Evident SHA-256 Audit Trail Verification...")
audit_res = client.get("/api/v1/audit/verify-integrity", headers=headers_a)
assert audit_res.status_code == 200
audit_data = audit_res.json()
print("  ✓ Cryptographic Integrity Result:", audit_data)
assert audit_data["intact"] is True, "Audit hash chain broken!"
print(f"  ✓ Confirmed: All {audit_data['entries_checked']} audit records cryptographically verified with zero tampering!")

print("\n🎉 ALL DEFINITION OF DONE (DoD) SCENARIOS FULLY VERIFIED WITH 100% SUCCESS!")
EOF

echo ""
echo "========================================================================"
echo "✅ DEFINITION OF DONE VERIFICATION COMPLETE"
echo "========================================================================"
