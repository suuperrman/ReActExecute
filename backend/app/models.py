import json
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


# ---------- SQLAlchemy ORM 模型 ----------

class NoteORM(Base):
    __tablename__ = "notes"

    # UUID 字符串主键，应用层生成
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 标签存 JSON 数组字符串，如 '["技术","FastAPI"]'
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )


class AgentSessionORM(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="新会话")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )


class AgentMessageORM(Base):
    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user / assistant
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 该轮工具调用步骤的 JSON（仅 assistant 消息可能有）
    steps_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------- Pydantic Schema ----------

class NoteCreate(BaseModel):
    title: str = Field(..., max_length=200, description="笔记标题")
    content: str = Field(default="", description="Markdown 正文")
    tags: Optional[list[str]] = Field(None, description="手动指定标签；不传则自动生成")


class NoteUpdate(BaseModel):
    """所有字段可选，支持部分更新"""
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    tags: Optional[list[str]] = None


class NoteOut(BaseModel):
    id: str
    title: str
    content: str
    tags: list[str]
    summary: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tags", mode="before")
    @classmethod
    def _parse_tags(cls, v):
        """ORM 里 tags 是 JSON 字符串，转成 list；已是 list 则原样返回"""
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        return []


class NoteList(BaseModel):
    total: int
    items: list[NoteOut]