"""
海军标准 RAG 智能体 — 全局配置文件
统一管理数据库、大模型、向量库、应用全部参数
"""

import os

# ============================================================
# 数据库配置 (PostgreSQL + pgvector)
# ============================================================
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5433"))
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "pgvector")

DB_MIN_CONN = 1
DB_MAX_CONN = 5

# ============================================================
# 向量库配置
# ============================================================
VECTOR_DIMENSIONS = 768
VECTOR_TABLE = "vector_st"
MAX_DOCUMENT_BATCH_SIZE = 24  # 增大批次减少encode调用次数
INDEX_TYPE = "HNSW"
DISTANCE_TYPE = "COSINE_DISTANCE"

# ============================================================
# 大模型配置 (阿里云百炼 — Demo阶段)
# ============================================================
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-98a311032b374edd914f4e0f71f17d30")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")
LLM_MAX_TOKENS = 4096
LLM_TEMPERATURE = 0.1  # 低温度保证严谨性

# 离线大模型开关（预留）
OFFLINE_MODE = os.getenv("OFFLINE_MODE", "false").lower() == "true"
OFFLINE_MODEL_PATH = os.getenv("OFFLINE_MODEL_PATH", "")

# ============================================================
# 嵌入模型配置
# ============================================================
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-base-zh-v1.5")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")  # cpu / cuda
EMBEDDING_NORMALIZE = True

# 英文嵌入扩展（预留）
EN_EMBEDDING_MODEL_NAME = os.getenv("EN_EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")

# ============================================================
# 文档处理配置
# ============================================================
CHUNK_SIZE = 800  # 分块目标大小（字符数）
CHUNK_OVERLAP = 100  # 块间重叠
SUPPORTED_FORMATS = ["pdf", "docx", "txt"]
MAX_UPLOAD_SIZE_MB = 50
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "uploads")

# ============================================================
# 检索配置
# ============================================================
RETRIEVAL_TOP_K = 10
RERANK_TOP_K = 5
HYBRID_KEYWORD_WEIGHT = 0.3  # 关键词检索权重
HYBRID_SEMANTIC_WEIGHT = 0.7  # 语义检索权重

# 文档状态优先级权重 (RRF融合用)
STATUS_PRIORITY = {
    "现行有效": 1.0,
    "修订中": 0.8,
    "废止": 0.5,
}

# ============================================================
# 应用配置
# ============================================================
APP_TITLE = "海军标准 RAG 智能体"
APP_LOGO = "⚓"
APP_VERSION = "1.0.0"

# 默认账号
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "navy123456"

# 日志
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_MAX_DAYS = 30
