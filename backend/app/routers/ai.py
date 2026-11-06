"""AI 辅助接口：润色 / 续写 / 生成标题 / 摘要"""
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..llm import chat

router = APIRouter(prefix="/api/ai", tags=["ai"])

MAX_INPUT_LEN = 20000


class TransformRequest(BaseModel):
    action: Literal["polish", "continue", "title", "summary"] = Field(..., description="要执行的动作")
    text: str = Field(..., description="输入文本")
    instruction: Optional[str] = Field(None, description="用户自定义附加指令")


class TransformResponse(BaseModel):
    result: str


# 各动作对应的系统提示词
PROMPTS = {
    "polish": (
        "你是一个专业的中文写作助手。请润色用户给出的文本，"
        "保持原意不变，优化表达、语句流畅度与标点使用。"
        "如果原文是 Markdown，保留原有的 Markdown 格式与结构。"
        "只输出润色后的完整文本，不要任何解释、前言或后缀。"
    ),
    "continue": (
        "你是一个中文写作助手。请基于用户给出的已有内容自然续写，"
        "保持与原文相同的语言、语气和 Markdown 格式风格。"
        "只输出续写的部分，不要重复原文，不要任何解释。"
    ),
    "title": (
        "你是一个标题生成器。根据用户给出的内容生成一个标题，"
        "要求：不超过 12 个汉字；准确概括核心内容；不加引号、不加句号、不加任何解释。"
        "只输出标题本身。"
    ),
    "summary": (
        "你是一个摘要生成器。用三句话概括用户给出的内容，"
        "第一句说主题，第二句说关键点，第三句说结论或用途。"
        "只输出摘要正文，不要列表符号，不要任何解释。"
    ),
}


@router.post("/transform", response_model=TransformResponse)
async def transform(payload: TransformRequest):
    """调用 LLM 对文本做一次变换"""
    text = payload.text.strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文本内容不能为空")
    if len(text) > MAX_INPUT_LEN:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"文本过长（{len(text)} 字符），上限 {MAX_INPUT_LEN}",
        )

    system_prompt = PROMPTS[payload.action]
    user_prompt = text
    if payload.instruction:
        user_prompt = f"{text}\n\n[附加要求] {payload.instruction}"

    try:
        result = await chat(system_prompt, user_prompt)
    except Exception as e:
        # DeepSeek 高峰期会返回 503/500 "Service is too busy"，重试后仍失败
        code = getattr(e, "status_code", None)
        if code == 429 or (code is not None and code >= 500):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                f"模型服务暂时繁忙（DeepSeek 返回 {code}），自动重试后仍未成功，请稍后再试。",
            ) from e
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"LLM 调用失败：{type(e).__name__}: {e}",
        ) from e

    return TransformResponse(result=result)
