from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import API_TOKEN
from .database import Base, engine
from .routers.agent import router as agent_router
from .routers.ai import router as ai_router
from .routers.notes import router as notes_router
from .routers.rag import router as rag_router


async def _run_migrations(conn) -> None:
    """SQLite 幂等迁移：给已存在的 notes 表补 tags / summary 列"""
    migrations = [
        "ALTER TABLE notes ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE notes ADD COLUMN summary TEXT",
    ]
    for sql in migrations:
        try:
            await conn.exec_driver_sql(sql)
        except Exception:
            # 列已存在（SQLite 报 duplicate column name），跳过
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时建表 + 迁移，关闭时释放引擎"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _run_migrations(conn)
    yield
    await engine.dispose()


app = FastAPI(title="Markdown Notes API", version="0.2.0", lifespan=lifespan)

# CORS：允许 Vite dev server（前端）跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 简易 API Token 鉴权（默认关闭，见 config.API_TOKEN）
@app.middleware("http")
async def api_token_middleware(request: Request, call_next):
    if API_TOKEN:
        path = request.url.path
        if path not in ("/", "/docs", "/openapi.json", "/redoc") \
                and not path.startswith("/docs") and not path.startswith("/openapi.json"):
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {API_TOKEN}":
                return JSONResponse(status_code=401, content={"detail": "未授权：缺少或错误的 API Token"})
    return await call_next(request)


app.include_router(notes_router)
app.include_router(ai_router)
app.include_router(agent_router)
app.include_router(rag_router)


@app.get("/")
def health_check():
    return {"status": "ok", "service": "markdown-notes"}