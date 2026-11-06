"""ReAct Agent 多轮对话接口（含 SSE 流式）"""
import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent.loop import run_react, run_react_events
from ..database import get_db
from ..models import AgentMessageORM, AgentSessionORM

router = APIRouter(prefix="/api/agent", tags=["agent"])

HISTORY_LIMIT = 20


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="给 Agent 的自然语言指令")
    session_id: Optional[str] = Field(None, description="会话 id；不传则新建会话")


class AgentStep(BaseModel):
    step: int
    tool: str
    arguments: dict
    result: Any
    ok: bool


class ChatResponse(BaseModel):
    session_id: str
    answer: str = Field(..., description="Agent 的最终回答")
    steps: list[AgentStep] = Field(default_factory=list, description="执行过程中每一步的工具调用")
    stopped_reason: str = Field(..., description="finished=正常结束 / max_steps=超出步数上限")


# ---------- 会话 / 消息持久化 ----------

async def _get_or_create_session(db: AsyncSession, session_id: Optional[str], title: str) -> AgentSessionORM:
    if session_id:
        s = await db.get(AgentSessionORM, session_id)
        if s is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"会话 {session_id} 不存在")
        return s
    s = AgentSessionORM(title=title[:20] or "新会话")
    db.add(s)
    await db.flush()
    return s


async def _load_history(db: AsyncSession, session_id: str) -> list[dict]:
    """按时间正序加载最近若干条 user/assistant 对话"""
    rows = (
        await db.scalars(
            select(AgentMessageORM)
            .where(AgentMessageORM.session_id == session_id)
            .order_by(AgentMessageORM.id.desc())
            .limit(HISTORY_LIMIT)
        )
    ).all()
    rows = list(reversed(rows))
    return [{"role": r.role, "content": r.content} for r in rows]


async def _save_message(
    db: AsyncSession, session: AgentSessionORM,
    role: str, content: str, steps_json: Optional[str] = None,
) -> None:
    db.add(AgentMessageORM(
        session_id=session.id, role=role, content=content, steps_json=steps_json,
    ))
    session.updated_at = datetime.now(timezone.utc)
    await db.flush()


# ---------- 路由 ----------

@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: AsyncSession = Depends(get_db)):
    """多轮对话：带 session_id 时续接历史上下文"""
    message = payload.message.strip()
    if not message:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "消息不能为空")

    session = await _get_or_create_session(db, payload.session_id, message)
    history = await _load_history(db, session.id)

    # 保存本轮用户消息
    await _save_message(db, session, "user", message)

    try:
        result = await run_react(message, db, history=history)
    except Exception as e:
        code = getattr(e, "status_code", None)
        if code == 429 or (code is not None and code >= 500):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                f"模型服务暂时繁忙（DeepSeek 返回 {code}），自动重试后仍未成功，请稍后再试。",
            ) from e
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Agent 执行失败：{type(e).__name__}: {e}",
        ) from e

    # 保存助手回答（含工具步骤 JSON）
    steps_json = json.dumps(result["steps"], ensure_ascii=False, default=str)
    await _save_message(db, session, "assistant", result["answer"], steps_json)

    return ChatResponse(
        session_id=session.id,
        answer=result["answer"],
        steps=result["steps"],
        stopped_reason=result["stopped_reason"],
    )


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, db: AsyncSession = Depends(get_db)):
    """SSE 流式版：实时推送工具执行步骤与最终答案"""
    message = payload.message.strip()
    if not message:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "消息不能为空")

    session = await _get_or_create_session(db, payload.session_id, message)
    history = await _load_history(db, session.id)
    await _save_message(db, session, "user", message)

    async def gen():
        steps: list[dict] = []
        answer = ""
        stopped = "finished"
        try:
            async for ev in run_react_events(message, db, history=history):
                if ev["type"] == "step":
                    steps.append({
                        "step": ev["step"], "tool": ev["tool"],
                        "arguments": ev["arguments"], "result": ev["result"], "ok": ev["ok"],
                    })
                    yield f"data: {json.dumps({'type': 'step', 'step': ev['step'], 'tool': ev['tool'], 'arguments': ev['arguments'], 'result': ev['result'], 'ok': ev['ok']}, ensure_ascii=False, default=str)}\n\n"
                elif ev["type"] == "answer":
                    answer = ev["content"]
                    stopped = ev["stopped_reason"]
                    yield f"data: {json.dumps({'type': 'answer', 'content': answer}, ensure_ascii=False)}\n\n"

            # 保存助手回答
            steps_json = json.dumps(steps, ensure_ascii=False, default=str)
            await _save_message(db, session, "assistant", answer, steps_json)
            yield f"data: {json.dumps({'type': 'done', 'session_id': session.id, 'stopped_reason': stopped}, ensure_ascii=False)}\n\n"
        except Exception as e:
            msg = f"Agent 执行失败：{type(e).__name__}: {e}"
            yield f"data: {json.dumps({'type': 'error', 'message': msg}, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------- 会话管理 ----------

@router.get("/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    """按更新时间倒序列出所有会话"""
    rows = (
        await db.scalars(
            select(AgentSessionORM).order_by(AgentSessionORM.updated_at.desc())
        )
    ).all()
    return [{
        "id": s.id,
        "title": s.title,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    } for s in rows]


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """返回会话详情及消息列表"""
    s = await db.get(AgentSessionORM, session_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"会话 {session_id} 不存在")
    rows = (
        await db.scalars(
            select(AgentMessageORM)
            .where(AgentMessageORM.session_id == session_id)
            .order_by(AgentMessageORM.id.asc())
        )
    ).all()
    messages = []
    for r in rows:
        messages.append({
            "id": r.id,
            "role": r.role,
            "content": r.content,
            "steps": json.loads(r.steps_json) if r.steps_json else [],
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return {
        "id": s.id,
        "title": s.title,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        "messages": messages,
    }


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """删除会话及其消息"""
    s = await db.get(AgentSessionORM, session_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"会话 {session_id} 不存在")
    await db.execute(
        delete(AgentMessageORM).where(AgentMessageORM.session_id == session_id)
    )
    await db.delete(s)
    await db.flush()
    return None