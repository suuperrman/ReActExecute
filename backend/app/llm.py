"""LLM 客户端封装：统一管理 DeepSeek 的调用入口"""
import asyncio
import random

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from .config import BASE_URL, MODEL_NAME, OPENAI_API_KEY

_client: AsyncOpenAI | None = None

# 可重试的 HTTP 状态码：限流(429) 与上游临时故障(5xx)
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 5
BACKOFF_BASE = 1.5
BACKOFF_CAP = 10.0


def get_client() -> AsyncOpenAI:
    """懒加载单例客户端（FastAPI 异步路由下复用连接池）"""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=OPENAI_API_KEY,
            base_url=BASE_URL,
            timeout=60.0,
        )
    return _client


async def create_completion(**kwargs):
    """发起补全请求，对上游临时故障（503/429/超时）自动指数退避重试

    DeepSeek 高峰期会返回 503 "Service is too busy"，属于可重试的临时故障。
    """
    client = get_client()
    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            return await client.chat.completions.create(**kwargs)
        except (APITimeoutError, APIConnectionError) as e:
            last_exc = e
        except APIStatusError as e:
            if e.status_code not in RETRYABLE_STATUS:
                raise
            last_exc = e

        if attempt < MAX_RETRIES - 1:
            # 指数退避 + 随机抖动，避免多个请求同时重试撞在一起
            delay = min(BACKOFF_BASE ** (attempt + 1), BACKOFF_CAP)
            delay += random.uniform(0, 1)
            await asyncio.sleep(delay)

    raise last_exc  # type: ignore[misc]


async def chat(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 4000,
) -> str:
    """发起一次对话补全，返回模型输出的纯文本"""
    resp = await create_completion(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = resp.choices[0].message.content
    return (content or "").strip()
