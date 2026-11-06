"""测试 ReAct 循环（mock LLM 响应，不真实调用 DeepSeek）"""
from app.agent.loop import run_react
from app.agent.tools import execute_tool


class _FakeToolCall:
    def __init__(self, name, arguments):
        self.id = "call_test"
        self.type = "function"
        self.function = type("F", (), {"name": name, "arguments": arguments})()


class _FakeMsg:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, msg):
        self.message = msg


class _FakeResp:
    def __init__(self, msg):
        self.choices = [_FakeChoice(msg)]


async def test_react_calls_tool_then_answers(db_session, monkeypatch):
    """第一轮返回工具调用，第二轮返回最终答案"""
    responses = [
        _FakeResp(_FakeMsg(content=None, tool_calls=[_FakeToolCall("list_notes", "{}")])),
        _FakeResp(_FakeMsg(content="你有 3 篇笔记。")),
    ]
    it = iter(responses)

    async def fake_create_completion(**kwargs):
        return next(it)

    monkeypatch.setattr("app.agent.loop.create_completion", fake_create_completion)

    # 预置一篇笔记，让 list_notes 返回非空
    await execute_tool("create_note", {"title": "一篇笔记", "content": "内容"}, db_session)

    result = await run_react("我有哪些笔记？", db_session)

    assert result["stopped_reason"] == "finished"
    assert result["answer"] == "你有 3 篇笔记。"
    assert len(result["steps"]) == 1
    assert result["steps"][0]["tool"] == "list_notes"
    assert result["steps"][0]["ok"] is True


async def test_react_with_history_is_injected(db_session, monkeypatch):
    """历史消息应被插入到 system 与当前 user 之间"""
    captured = {}

    async def fake_create_completion(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _FakeResp(_FakeMsg(content="已处理。"))

    monkeypatch.setattr("app.agent.loop.create_completion", fake_create_completion)

    history = [{"role": "user", "content": "之前的问题"}, {"role": "assistant", "content": "之前的回答"}]
    await run_react("继续", db_session, history=history)

    msgs = captured["messages"]
    roles = [(m["role"], m["content"]) for m in msgs]
    assert msgs[0]["role"] == "system"
    assert ("user", "之前的问题") in roles
    assert ("assistant", "之前的回答") in roles
    # 当前 user 消息应排在历史之后
    assert roles.index(("user", "继续")) > roles.index(("assistant", "之前的回答"))