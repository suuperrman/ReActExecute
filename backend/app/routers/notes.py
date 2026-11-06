import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..llm import chat as llm_chat
from ..models import NoteCreate, NoteList, NoteORM, NoteOut, NoteUpdate

router = APIRouter(prefix="/api/notes", tags=["notes"])

TAG_PROMPT = (
    "你是标签生成器。根据笔记内容，输出 1~3 个最贴切的中文标签。"
    "标签是简短的名词短语（如：技术、FastAPI、读书、面试）。"
    "只输出一个 JSON 字符串数组，例如：[\"技术\",\"FastAPI\"]，不要任何解释。"
)


async def _auto_tag(title: str, content: str) -> list[str]:
    """调用 LLM 生成标签；任何失败都静默返回空列表，不影响保存主流程"""
    try:
        text = f"标题：{title}\n正文：{content[:500]}"
        raw = await llm_chat(TAG_PROMPT, text, temperature=0.2, max_tokens=60)
        start, end = raw.find("["), raw.rfind("]")
        if start != -1 and end != -1 and end > start:
            parsed = json.loads(raw[start:end + 1])
            if isinstance(parsed, list):
                return [str(t).strip() for t in parsed if str(t).strip()][:3]
    except Exception:
        pass
    return []


@router.get("", response_model=NoteList)
async def list_notes(
    page: int = 1,
    page_size: int = 20,
    tag: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """分页查询笔记列表（按更新时间倒序）；可用 tag 筛选"""
    if page < 1 or page_size < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "page / page_size 必须 >= 1")

    conditions = []
    if tag:
        conditions.append(NoteORM.tags.like(f'%"{tag}"%'))

    count_stmt = select(func.count()).select_from(NoteORM)
    stmt = select(NoteORM)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
        stmt = stmt.where(*conditions)

    total = await db.scalar(count_stmt)
    stmt = (
        stmt.order_by(NoteORM.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.scalars(stmt)).all()
    return NoteList(total=total or 0, items=[NoteOut.model_validate(r) for r in rows])


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(note_id: str, db: AsyncSession = Depends(get_db)):
    """获取单篇笔记"""
    row = await db.get(NoteORM, note_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"笔记 {note_id} 不存在")
    return NoteOut.model_validate(row)


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(payload: NoteCreate, db: AsyncSession = Depends(get_db)):
    """新建笔记（未显式指定 tags 时自动打标签）"""
    if payload.tags is not None:
        tags = payload.tags
    else:
        tags = await _auto_tag(payload.title, payload.content)

    row = NoteORM(
        title=payload.title,
        content=payload.content,
        tags=json.dumps(tags, ensure_ascii=False),
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)          # 刷新获取 db 生成的时间戳，避免 MissingGreenlet
    return NoteOut.model_validate(row)


@router.put("/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: str,
    payload: NoteUpdate,
    db: AsyncSession = Depends(get_db),
):
    """全量更新（触发自动保存）；标题/正文变化且未显式传 tags 时重新打标签"""
    row = await db.get(NoteORM, note_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"笔记 {note_id} 不存在")

    update_data = payload.model_dump(exclude_unset=True)

    # tags 单独处理：显式传入则用传入值；否则若标题/正文变了，自动重打
    if "tags" in update_data:
        tags = update_data.pop("tags")
        row.tags = json.dumps(tags or [], ensure_ascii=False)
    elif "title" in update_data or "content" in update_data:
        new_title = update_data.get("title", row.title)
        new_content = update_data.get("content", row.content)
        auto_tags = await _auto_tag(new_title, new_content)
        row.tags = json.dumps(auto_tags, ensure_ascii=False)

    for field, value in update_data.items():
        setattr(row, field, value)

    await db.flush()
    await db.refresh(row)          # 刷新 updated_at，避免懒加载异常
    return NoteOut.model_validate(row)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: str, db: AsyncSession = Depends(get_db)):
    """删除笔记"""
    row = await db.get(NoteORM, note_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"笔记 {note_id} 不存在")
    await db.delete(row)
    await db.flush()
    return None