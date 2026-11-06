"""RAG 问答接口：基于笔记库内容回答问题"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..llm import chat as llm_chat
from ..models import NoteORM

router = APIRouter(prefix="/api/rag", tags=["rag"])

CONTEXT_NOTE_LIMIT = 15
CONTEXT_SNIPPET_CHARS = 400

RAG_PROMPT = (
    "你是个人知识库的问答助手。请严格基于下面提供的笔记内容回答问题，"
    "不要编造笔记里没有的事实。如果笔记中找不到相关信息，请如实说明。\n\n"
    "笔记内容：\n{context}\n\n"
    "回答要求：用中文、简洁、分点。结尾单独一行输出「参考笔记：」后列出你引用的笔记标题（逗号分隔）。"
)


@router.post("/ask")
async def ask(
    payload: "AskRequest",
    db: AsyncSession = Depends(get_db),
):
    """基于笔记库内容回答用户问题"""
    question = payload.question.strip()
    if not question:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "问题不能为空")

    rows = (
        await db.scalars(
            select(NoteORM).order_by(NoteORM.updated_at.desc()).limit(CONTEXT_NOTE_LIMIT)
        )
    ).all()

    if not rows:
        return {"answer": "你的笔记库还是空的，先记录一些内容再来问我吧。", "sources": []}

    context_parts = []
    for n in rows:
        snippet = n.content[:CONTEXT_SNIPPET_CHARS]
        context_parts.append(f"[{n.id}] 标题：{n.title}\n{snippet}")
    context = "\n\n".join(context_parts)

    system_prompt = RAG_PROMPT.format(context=context)
    try:
        answer = await llm_chat(system_prompt, question, temperature=0.3, max_tokens=1000)
    except Exception as e:
        code = getattr(e, "status_code", None)
        if code == 429 or (code is not None and code >= 500):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                f"模型服务暂时繁忙（DeepSeek 返回 {code}），请稍后再试。",
            ) from e
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"RAG 问答失败：{type(e).__name__}: {e}",
        ) from e

    sources = [{"id": n.id, "title": n.title} for n in rows]
    return {"answer": answer, "sources": sources}


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000, description="用户问题")