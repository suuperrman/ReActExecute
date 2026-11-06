"""ReAct Agent 的工具定义（OpenAI function calling schema）与执行器"""
import json
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import NoteORM

# ---------- 工具 schema（传给 LLM 的 tools 参数） ----------

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_notes",
            "description": "列出笔记库中的笔记。可用 keyword 对标题和正文做模糊匹配。返回笔记的 id、标题、更新时间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "模糊匹配关键词，匹配标题和正文。留空则返回全部笔记。",
                    },
                    "page_size": {
                        "type": "integer",
                        "description": "本次最多返回多少条，默认 20，最大 100。",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_note",
            "description": "按笔记 id 读取一篇笔记的完整内容（标题 + Markdown 正文）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {
                        "type": "string",
                        "description": "笔记的 UUID id，来自 list_notes 的返回结果。",
                    }
                },
                "required": ["note_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_note",
            "description": "新建一篇笔记并保存到笔记库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "笔记标题"},
                    "content": {"type": "string", "description": "笔记正文，Markdown 格式"},
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_note",
            "description": "更新已存在的笔记。title 和 content 都是可选的，只传需要修改的字段；content 传入时会整体替换正文。",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "笔记的 UUID id"},
                    "title": {"type": "string", "description": "新的标题"},
                    "content": {"type": "string", "description": "新的完整正文（Markdown）"},
                },
                "required": ["note_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_note",
            "description": "删除一篇笔记。破坏性操作，仅在用户明确要求时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "要删除的笔记 UUID id"},
                },
                "required": ["note_id"],
            },
        },
    },
]


# ---------- 工具执行器 ----------

def _note_brief(note: NoteORM) -> dict:
    """列表用的精简结构"""
    return {
        "id": note.id,
        "title": note.title,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


def _note_full(note: NoteORM) -> dict:
    """详情用的完整结构"""
    return {
        "id": note.id,
        "title": note.title,
        "content": note.content,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


async def execute_tool(name: str, arguments: dict, db: AsyncSession) -> Any:
    """根据工具名分发执行，返回可 JSON 序列化的结果"""
    args = arguments or {}

    if name == "list_notes":
        keyword = (args.get("keyword") or "").strip()
        try:
            page_size = int(args.get("page_size") or 20)
        except (TypeError, ValueError):
            page_size = 20
        page_size = max(1, min(page_size, 100))

        stmt = select(NoteORM).order_by(NoteORM.updated_at.desc()).limit(page_size)
        count_stmt = select(func.count()).select_from(NoteORM)

        if keyword:
            like = f"%{keyword}%"
            stmt = stmt.where(
                or_(NoteORM.title.like(like), NoteORM.content.like(like))
            )
            count_stmt = count_stmt.where(
                or_(NoteORM.title.like(like), NoteORM.content.like(like))
            )

        rows = (await db.scalars(stmt)).all()
        total = await db.scalar(count_stmt)
        return {
            "total": total or 0,
            "returned": len(rows),
            "notes": [_note_brief(r) for r in rows],
        }

    if name == "get_note":
        note_id = str(args.get("note_id") or "").strip()
        if not note_id:
            raise ValueError("note_id 不能为空")
        note = await db.get(NoteORM, note_id)
        if note is None:
            return {"error": f"笔记 {note_id} 不存在"}
        return _note_full(note)

    if name == "create_note":
        title = str(args.get("title") or "").strip()
        content = str(args.get("content") or "")
        if not title:
            raise ValueError("title 不能为空")
        note = NoteORM(title=title, content=content)
        db.add(note)
        await db.flush()
        await db.refresh(note)
        return {"created": True, "note": _note_full(note)}

    if name == "update_note":
        note_id = str(args.get("note_id") or "").strip()
        if not note_id:
            raise ValueError("note_id 不能为空")
        note = await db.get(NoteORM, note_id)
        if note is None:
            return {"error": f"笔记 {note_id} 不存在"}

        if "title" in args and args["title"] is not None:
            new_title = str(args["title"]).strip()
            if not new_title:
                raise ValueError("title 不能为空")
            note.title = new_title
        if "content" in args and args["content"] is not None:
            note.content = str(args["content"])

        await db.flush()
        await db.refresh(note)
        return {"updated": True, "note": _note_full(note)}

    if name == "delete_note":
        note_id = str(args.get("note_id") or "").strip()
        if not note_id:
            raise ValueError("note_id 不能为空")
        note = await db.get(NoteORM, note_id)
        if note is None:
            return {"error": f"笔记 {note_id} 不存在"}
        title = note.title
        await db.delete(note)
        await db.flush()
        return {"deleted": True, "id": note_id, "title": title}

    raise ValueError(f"未知工具：{name}")


def dumps_result(value: Any) -> str:
    """把工具结果序列化成喂回 LLM 的 JSON 字符串"""
    return json.dumps(value, ensure_ascii=False, default=str)
