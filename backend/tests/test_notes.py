"""笔记 CRUD + 标签筛选 + 自动打标签的测试"""
import json

import pytest


@pytest.fixture
def mock_tags(monkeypatch):
    """让自动打标签返回固定标签，不真实调用 LLM"""
    async def fake_chat(system_prompt, user_prompt, **kwargs):
        return '["测试标签"]'
    monkeypatch.setattr("app.routers.notes.llm_chat", fake_chat)
    return fake_chat


async def test_create_note_with_auto_tag(client, mock_tags):
    resp = await client.post("/api/notes", json={"title": "测试", "content": "正文"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "测试"
    assert data["tags"] == ["测试标签"]


async def test_create_note_with_explicit_tag(client):
    resp = await client.post(
        "/api/notes", json={"title": "T", "content": "c", "tags": ["Python"]}
    )
    assert resp.status_code == 201
    assert resp.json()["tags"] == ["Python"]


async def test_list_and_tag_filter(client, mock_tags):
    await client.post("/api/notes", json={"title": "笔记A", "content": "x"})
    await client.post("/api/notes", json={"title": "笔记B", "content": "y", "tags": ["Go"]})
    await client.post("/api/notes", json={"title": "笔记C", "content": "z", "tags": ["Go"]})

    # 不过滤：3 条
    r = await client.get("/api/notes")
    assert r.json()["total"] == 3

    # 按 tag=Go：2 条（显式打标签的两条）
    r = await client.get("/api/notes", params={"tag": "Go"})
    assert r.json()["total"] == 2
    titles = {n["title"] for n in r.json()["items"]}
    assert titles == {"笔记B", "笔记C"}

    # 不存在的 tag：0 条
    r = await client.get("/api/notes", params={"tag": "不存在"})
    assert r.json()["total"] == 0


async def test_get_update_delete(client, mock_tags):
    r = await client.post("/api/notes", json={"title": "旧标题", "content": "旧正文"})
    assert r.status_code == 201
    note_id = r.json()["id"]

    # GET
    r = await client.get(f"/api/notes/{note_id}")
    assert r.json()["title"] == "旧标题"

    # PUT 更新
    r = await client.put(f"/api/notes/{note_id}", json={"title": "新标题"})
    assert r.status_code == 200
    assert r.json()["title"] == "新标题"

    # DELETE
    r = await client.delete(f"/api/notes/{note_id}")
    assert r.status_code == 204

    r = await client.get(f"/api/notes/{note_id}")
    assert r.status_code == 404


async def test_get_not_found(client):
    r = await client.get("/api/notes/不存在")
    assert r.status_code == 404