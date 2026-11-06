import os
from pathlib import Path

from dotenv import load_dotenv

# 加载 backend 目录下的 .env
# override=True：让项目级 .env 优先于机器/用户级系统环境变量
# （本机系统里存在其他平台的 OPENAI_API_KEY，会默认覆盖 .env 中的 DeepSeek key）
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

# 数据库（SQLite 文件放在 backend/data/ 下）
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DATA_DIR}/notes.db")

# LLM 配置（DeepSeek 官方）
BASE_URL = os.getenv("BASE_URL", "https://api.deepseek.com")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-chat")

# 简易 API Token 鉴权（默认空 = 不启用）
# 非空时，请求需带 Authorization: Bearer <API_TOKEN>
API_TOKEN = os.getenv("API_TOKEN", "")
