"""直接测试 agent 工具执行器（纯 DB 层，不涉及 LLM）"""
from app.agent.tools import execute_tool
from app.models import NoteORM


async def test_create_and_get_note(db_session):
    r = await execute_tool("create_note", {"title": "工具测试", "content": "内容"}, db_session)
    assert r["created"] is True
    note_id = r["note"]["id"]

    r2 = await execute_tool("get_note", {"note_id": note_id}, db_session)
    assert r2["title"] == "工具测试"
    assert r2["content"] == "内容"


async def test_list_notes_with_keyword(db_session):
    await execute_tool("create_note", {"title": "关于读书", "content": "瞎写"}, db_session)
    await execute_tool("create_note", {"title": "关于代码", "content": "FastAPI"}, db_session)

    r = await execute_tool("list_notes", {"keyword": "读书"}, db_session)
    assert r["returned"] == 1
    assert r["notes"][0]["title"] == "关于读书"


async def test_update_note(db_session):
    r = await execute_tool("create_note", {"title": "旧", "content": "c"}, db_session)
    note_id = r["note"]["id"]

    r2 = await execute_tool("update_note", {"note_id": note_id, "title": "新"}, db_session)
    assert r2["updated"] is True
    assert r2["note"]["title"] == "新"


async def test_delete_note(db_session):
    r = await execute_tool("create_note", {"title": "待删", "content": "c"}, db_session)
    note_id = r["note"]["id"]

    r2 = await execute_tool("delete_note", {"note_id": note_id}, db_session)
    assert r2["deleted"] is True

    r3 = await execute_tool("get_note", {"note_id": note_id}, db_session)
    assert "error" in r3


async def test_get_missing_note(db_session):
    r = await execute_tool("get_note", {"note_id": "不存在的id"}, db_session)
    assert "error" in r


async def test_unknown_tool(db_session):
    import pytest as _pytest
    with _pytest.raises(ValueError):
        await execute_tool("not_a_tool", {}, db_session)