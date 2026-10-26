from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import ChatRequest, ChatResponse
from app.security import require_auth, AuthContext
from app.chat_agent import chat_agent

router = APIRouter(prefix="/chat", tags=["Agent Chat Interface"])

@router.post("", response_model=ChatResponse)
async def chat_with_agent(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_auth)
):
    """
    Direct conversational interface with the multi-MCP Autonomous Assistant.
    Executes tool calls through the MCP Gateway under the logged-in user's identity,
    strictly respecting user role permissions and recording to the tamper-evident audit log.
    """
    messages_payload = [m.model_dump() for m in req.messages]
    result = await chat_agent.chat_completion(messages_payload, auth=auth, db=db, model=req.model)
    return result
