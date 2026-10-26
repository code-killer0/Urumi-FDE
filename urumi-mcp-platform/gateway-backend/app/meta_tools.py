import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import UpstreamServer, ServerStatus

logger = logging.getLogger("meta-tools")

META_TOOLS_DEFINITIONS = [
    {
        "name": "gateway__search_tools",
        "description": "Meta-tool search: Query the gateway catalog to discover relevant tools across all upstream servers by natural language keyword or task description.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keyword or capability query (e.g. 'order', 'coupon', 'inventory', 'alert', 'discount')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of tools to return (default 10)",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "gateway__execute_tool",
        "description": "Meta-tool execution: Dynamically invoke any registered upstream MCP tool by qualified name (e.g. 'woo__list_orders') after discovering it via search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "Fully qualified tool name in {server_slug}__{tool_name} format"
                },
                "arguments": {
                    "type": "object",
                    "description": "JSON arguments matching the discovered tool's inputSchema"
                }
            },
            "required": ["tool_name", "arguments"]
        }
    }
]

async def search_gateway_tools(query: str, limit: int, db: AsyncSession) -> List[Dict[str, Any]]:
    stmt = select(UpstreamServer).where(UpstreamServer.enabled == True)
    res = await db.execute(stmt)
    servers = res.scalars().all()

    query_lower = query.lower().strip()
    matches = []

    for s in servers:
        for t in (s.cached_tools or []):
            orig_name = t.get("name", "")
            desc = t.get("description", "")
            q_name = f"{s.slug}__{orig_name}"
            # Check query in name, description, or server slug
            score = 0
            if query_lower in orig_name.lower():
                score += 5
            if query_lower in desc.lower():
                score += 3
            if query_lower in s.slug.lower():
                score += 2

            if score > 0 or query_lower in ("all", "*"):
                matches.append({
                    "score": score,
                    "name": q_name,
                    "server": s.slug,
                    "description": desc,
                    "inputSchema": t.get("inputSchema", {})
                })

    # Sort by relevance score
    matches.sort(key=lambda x: x["score"], reverse=True)
    results = matches[:limit]
    for m in results:
        m.pop("score", None)
    return results
