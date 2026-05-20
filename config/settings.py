"""
全局配置 — 数据库、大模型、向量库、应用参数
"""

import os

# ============================================================
# 数据库 (PostgreSQL + pgvector)
# ============================================================
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5433"))
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "pgvector")
DB_MIN_CONN = 1
DB_MAX_CONN = 5

# ============================================================
# 向量库
# ============================================================
VECTOR_DIMENSIONS = 768
VECTOR_TABLE = "vector_st"
MAX_DOCUMENT_BATCH_SIZE = 24

# ============================================================
# 大模型 (阿里云百炼)
# ============================================================
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-98a311032b374edd914f4e0f71f17d30")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")
LLM_MAX_TOKENS = 4096
LLM_TEMPERATURE = 0.1

OFFLINE_MODE = os.getenv("OFFLINE_MODE", "false").lower() == "true"
OFFLINE_MODEL_PATH = os.getenv("OFFLINE_MODEL_PATH", "")

# ============================================================
# 嵌入模型
# ============================================================
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-base-zh-v1.5")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")
EMBEDDING_NORMALIZE = True
EN_EMBEDDING_MODEL_NAME = os.getenv("EN_EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")

# ============================================================
# 文档处理
# ============================================================
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
SUPPORTED_FORMATS = ["pdf", "docx", "txt"]
MAX_UPLOAD_SIZE_MB = 50
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "uploads")

# ============================================================
# 检索
# ============================================================
HYBRID_KEYWORD_WEIGHT = 0.3
HYBRID_SEMANTIC_WEIGHT = 0.7
STATUS_PRIORITY = {"现行有效": 1.0, "修订中": 0.8, "废止": 0.5}

# ============================================================
# 应用
# ============================================================
APP_TITLE = "海军标准 RAG 智能体"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "navy123456"

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_MAX_DAYS = 30
