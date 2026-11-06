"""ReAct 主循环：让 LLM 自主决定调用工具，直到得出最终答案"""
import json
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import MODEL_NAME
from ..llm import create_completion
from .prompt import SYSTEM_PROMPT
from .tools import TOOL_SCHEMAS, dumps_result, execute_tool

MAX_STEPS = 8


async def run_react_events(
    user_message: str,
    db: AsyncSession,
    history: list[dict] | None = None,
    max_steps: int = MAX_STEPS,
) -> AsyncGenerator[dict, None]:
    """
    ReAct 事件流（异步生成器）：
    - yield {"type": "step", "step", "tool", "arguments", "result", "ok"} 每执行完一个工具
    - yield {"type": "answer", "content", "stopped_reason"} 得到最终答案后
    异常会向上抛出，由调用方决定如何呈现。
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    # 多轮对话：把历史 user/assistant 消息插入到当前 user 之前
    if history:
        for h in history:
            role = h.get("role")
            content = h.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})

    for step_no in range(1, max_steps + 1):
        resp = await create_completion(
            model=MODEL_NAME,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0.2,
        )
        msg = resp.choices[0].message

        # 把 assistant 这一轮追加进上下文（必须保留 tool_calls 原文）
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": msg.content or "",
        }
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_msg)

        # 没有工具调用 → 模型已经给出最终答案
        if not msg.tool_calls:
            yield {
                "type": "answer",
                "content": (msg.content or "").strip(),
                "stopped_reason": "finished",
            }
            return

        # 执行本轮请求的所有工具
        for tc in msg.tool_calls:
            raw_args = tc.function.arguments or "{}"
            try:
                arguments = json.loads(raw_args)
            except json.JSONDecodeError:
                arguments = {}
                result: Any = {"error": f"工具参数不是合法 JSON：{raw_args}"}
                ok = False
            else:
                try:
                    result = await execute_tool(tc.function.name, arguments, db)
                    ok = not (isinstance(result, dict) and "error" in result)
                except Exception as e:
                    result = {"error": f"{type(e).__name__}: {e}"}
                    ok = False

            yield {
                "type": "step",
                "step": step_no,
                "tool": tc.function.name,
                "arguments": arguments,
                "result": result,
                "ok": ok,
            }

            # 工具结果必须以 role="tool" + 对应的 tool_call_id 回填
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": dumps_result(result),
            })

    yield {
        "type": "answer",
        "content": "已达到最大执行步数仍未得出结论，请把任务拆小一点再试。",
        "stopped_reason": "max_steps",
    }


async def run_react(
    user_message: str,
    db: AsyncSession,
    history: list[dict] | None = None,
    max_steps: int = MAX_STEPS,
) -> dict:
    """聚合版：把事件流收集成 {answer, steps, stopped_reason}"""
    steps: list[dict] = []
    answer = ""
    stopped_reason = "finished"

    async for ev in run_react_events(user_message, db, history, max_steps):
        if ev["type"] == "step":
            steps.append({
                "step": ev["step"],
                "tool": ev["tool"],
                "arguments": ev["arguments"],
                "result": ev["result"],
                "ok": ev["ok"],
            })
        elif ev["type"] == "answer":
            answer = ev["content"]
            stopped_reason = ev["stopped_reason"]

    return {"answer": answer, "steps": steps, "stopped_reason": stopped_reason}