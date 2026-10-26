import os
import json
import logging
import time
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models import UpstreamServer, UserRole, AuditOutcome
from app.security import AuthContext
from app.mcp_gateway import check_tool_permission, write_tamper_evident_audit_log
from app.upstream_manager import upstream_manager

logger = logging.getLogger("chat-agent")

class ChatAgent:
    """
    Intelligent Autonomous Tool-Calling AI Agent operating under the logged-in user's identity.
    Dispatches tool calls through the MCP Gateway to enforce role permissions
    and generates immutable audit trails for every agent action.
    """
    def __init__(self):
        pass

    async def get_tools_for_user(self, auth: AuthContext, db: AsyncSession) -> List[Dict[str, Any]]:
        """Fetch all tools accessible to the logged-in user based on role policies."""
        stmt = select(UpstreamServer).where(UpstreamServer.enabled == True)
        res = await db.execute(stmt)
        servers = res.scalars().all()

        openai_tools = []
        user_role = auth.user_role

        for s in servers:
            for t in (s.cached_tools or []):
                q_name = f"{s.slug}__{t.get('name')}"
                if not await check_tool_permission(user_role, q_name, db):
                    continue

                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": q_name,
                        "description": f"[{s.name}] {t.get('description', '')}",
                        "parameters": t.get("inputSchema", {"type": "object", "properties": {}})
                    }
                })

        return openai_tools

    async def execute_tool_for_user(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        auth: AuthContext,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Executes a tool call under the user's authenticated identity,
        enforcing role permissions and recording to the tamper-evident audit log.
        """
        start_time = time.monotonic()

        # Role permission check
        has_perm = await check_tool_permission(auth.user_role, tool_name, db)
        if not has_perm:
            duration_ms = (time.monotonic() - start_time) * 1000
            err_msg = f"Forbidden: role '{auth.user_role}' cannot execute '{tool_name}'."
            await write_tamper_evident_audit_log(
                db=db, auth=auth, auth_method="chat_session", server_slug=None,
                tool_name=tool_name, arguments=arguments, duration_ms=duration_ms,
                outcome=AuditOutcome.REJECTED_FORBIDDEN.value, error_message=err_msg
            )
            return {"error": err_msg, "isError": True}

        if "__" not in tool_name:
            return {"error": f"Invalid tool format: '{tool_name}'. Must be 'slug__tool_name'.", "isError": True}

        server_slug, target_tool = tool_name.split("__", 1)

        stmt = select(UpstreamServer).where(UpstreamServer.slug == server_slug)
        server = (await db.execute(stmt)).scalar_one_or_none()

        if not server:
            duration_ms = (time.monotonic() - start_time) * 1000
            await write_tamper_evident_audit_log(
                db=db, auth=auth, auth_method="chat_session", server_slug=server_slug,
                tool_name=target_tool, arguments=arguments, duration_ms=duration_ms,
                outcome=AuditOutcome.ERROR.value, error_message=f"Server '{server_slug}' not found"
            )
            return {"error": f"Upstream server '{server_slug}' not found", "isError": True}

        try:
            call_res = await upstream_manager.execute_tool_call(server, target_tool, arguments)
            duration_ms = call_res.get("latency_ms", (time.monotonic() - start_time) * 1000)
            await db.commit()

            await write_tamper_evident_audit_log(
                db=db, auth=auth, auth_method="chat_session", server_slug=server_slug,
                tool_name=target_tool, arguments=arguments, duration_ms=duration_ms,
                outcome=AuditOutcome.SUCCESS.value
            )
            return call_res.get("result", {})

        except Exception as exc:
            duration_ms = (time.monotonic() - start_time) * 1000
            await write_tamper_evident_audit_log(
                db=db, auth=auth, auth_method="chat_session", server_slug=server_slug,
                tool_name=target_tool, arguments=arguments, duration_ms=duration_ms,
                outcome=AuditOutcome.ERROR.value, error_message=str(exc)
            )
            return {"error": str(exc), "isError": True}

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        auth: AuthContext,
        db: AsyncSession,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Processes conversation turn using genuine multi-turn autonomous tool-calling.
        Operates strictly under the logged-in user's identity.
        """
        tools = await self.get_tools_for_user(auth, db)
        execution_trace = []

        gemini_key = (
            settings.GEMINI_API_KEY
            or settings.GOOGLE_API_KEY
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )
        if gemini_key:
            gemini_key = gemini_key.strip()
        openai_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
        if openai_key:
            openai_key = openai_key.strip()

        if not gemini_key and not openai_key:
            return {
                "message": {
                    "role": "assistant",
                    "content": (
                        f"Autonomous Chat Agent is currently offline: No LLM API key configured.\n\n"
                        f"To enable autonomous tool execution, please add `GEMINI_API_KEY=...` or `OPENAI_API_KEY=...` "
                        f"to `gateway-backend/.env`.\n\n"
                        f"You currently have {len(tools)} tools available under your '{auth.user_role}' role "
                        f"which can be accessed directly via the MCP protocol endpoint (`/mcp`) using your API key."
                    )
                },
                "tool_execution_trace": []
            }

        try:
            from openai import AsyncOpenAI

            if gemini_key:
                client_kwargs = {
                    "api_key": gemini_key,
                    "base_url": settings.LLM_BASE_URL or "https://generativelanguage.googleapis.com/v1beta/openai/"
                }
                primary_model = model or settings.LLM_MODEL or "gemini-flash-lite-latest"
            else:
                client_kwargs = {"api_key": openai_key}
                if settings.LLM_BASE_URL:
                    client_kwargs["base_url"] = settings.LLM_BASE_URL
                primary_model = model or settings.LLM_MODEL or "gpt-4o-mini"

            timeout_seconds = getattr(settings, "LLM_TIMEOUT_SECONDS", 60.0) or 60.0
            ai_client = AsyncOpenAI(**client_kwargs, timeout=timeout_seconds, max_retries=2)

            # Candidate model fallback list
            candidate_models = [primary_model]
            if gemini_key:
                for fallback in ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.5-pro"]:
                    if fallback not in candidate_models:
                        candidate_models.append(fallback)

            async def call_llm(kwargs: dict):
                last_err = None
                for cand in candidate_models:
                    kwargs["model"] = cand
                    try:
                        return await ai_client.chat.completions.create(**kwargs)
                    except Exception as err:
                        err_str = str(err).lower()
                        # If model is unavailable (503), not found (404), or high demand, try next model candidate
                        if any(kw in err_str for kw in ["503", "404", "high demand", "unavailable", "not found"]):
                            logger.warning(f"LLM model '{cand}' unavailable ({err}). Attempting fallback...")
                            last_err = err
                            continue
                        raise err
                if last_err:
                    raise last_err

            # System prompt providing context and tool guidelines
            system_prompt = (
                f"You are the autonomous Urumi Platform MCP Assistant. You are currently acting "
                f"under the authenticated identity of user {auth.user_email} with role '{auth.user_role}'.\n"
                f"You have access to tools across connected WooCommerce stores and operational microservices.\n"
                f"Always use the available tools to satisfy user queries accurately and report the real results.\n"
                f"When asked to create products or query orders, call the relevant tool with the parameters requested by the user."
            )

            # Clean and prepare conversation history
            conversation: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
            for m in messages:
                role = m.get("role", "user")
                if role in ("user", "assistant", "system"):
                    conversation.append({
                        "role": role,
                        "content": m.get("content") or ""
                    })

            # Autonomous Multi-Turn ReAct Loop (Up to 6 turns)
            max_turns = 6
            turn = 0

            while turn < max_turns:
                turn += 1

                call_kwargs = {
                    "messages": conversation,
                }
                if tools:
                    call_kwargs["tools"] = tools
                    call_kwargs["tool_choice"] = "auto"

                response = await call_llm(call_kwargs)
                choice = response.choices[0]
                msg = choice.message

                if not msg.tool_calls:
                    # Final response produced
                    return {
                        "message": {
                            "role": "assistant",
                            "content": msg.content or ""
                        },
                        "tool_execution_trace": execution_trace
                    }

                # Construct clean assistant message dump for conversation history
                assistant_dump: Dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [tc.model_dump() for tc in msg.tool_calls]
                }
                conversation.append(assistant_dump)

                # Execute all tools requested in this turn
                for tc in msg.tool_calls:
                    fn_name = tc.function.name
                    try:
                        fn_args = json.loads(tc.function.arguments or "{}")
                    except Exception:
                        fn_args = {}

                    tool_res = await self.execute_tool_for_user(fn_name, fn_args, auth, db)
                    execution_trace.append({
                        "tool": fn_name,
                        "arguments": fn_args,
                        "result": tool_res
                    })

                    content_str = json.dumps(tool_res) if not isinstance(tool_res, str) else tool_res
                    conversation.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": content_str
                    })

            # If max turns reached, generate final synthesis
            final_resp = await call_llm({
                "messages": conversation
            })
            return {
                "message": {
                    "role": "assistant",
                    "content": final_resp.choices[0].message.content or "Tool execution completed."
                },
                "tool_execution_trace": execution_trace
            }

        except Exception as e:
            logger.error(f"External LLM invocation error: {e}", exc_info=True)
            return {
                "message": {
                    "role": "assistant",
                    "content": f"LLM execution error: {str(e)}"
                },
                "tool_execution_trace": execution_trace
            }

chat_agent = ChatAgent()
