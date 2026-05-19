"""
嵌入模型封装 — BGE-base-zh-v1.5 768维
本地运行，支持批量编码和英文扩展
"""

import os
import threading
from typing import List

# 国内用户使用 HuggingFace 镜像加速下载
if not os.getenv("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from config.settings import (
    EMBEDDING_MODEL_NAME, EMBEDDING_DEVICE, EMBEDDING_NORMALIZE,
    VECTOR_DIMENSIONS, MAX_DOCUMENT_BATCH_SIZE,
    EN_EMBEDDING_MODEL_NAME,
)
from utils.logger import get_logger

logger = get_logger(__name__)

_model = None
_model_lock = threading.Lock()
_model_loaded = False

# 英文模型扩展（预留）
_en_model = None
_en_model_loaded = False


def _load_model():
    """延迟加载嵌入模型（首次调用时加载），优先使用本地缓存"""
    global _model, _model_loaded
    if _model_loaded:
        return

    with _model_lock:
        if _model_loaded:
            return

        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"正在加载嵌入模型: {EMBEDDING_MODEL_NAME} (镜像: {os.environ.get('HF_ENDPOINT', 'default')})")
            _model = SentenceTransformer(
                EMBEDDING_MODEL_NAME,
                device=EMBEDDING_DEVICE,
            )
            _model_loaded = True
            logger.info(f"嵌入模型加载完成，维度: {_model.get_sentence_embedding_dimension() if hasattr(_model, 'get_sentence_embedding_dimension') else VECTOR_DIMENSIONS}")
        except Exception as e:
            logger.error(f"嵌入模型加载失败: {e}")
            logger.error("请检查网络连接，或手动下载模型到本地后修改 EMBEDDING_MODEL_NAME 为本地路径")
            raise


def embed_texts(texts: List[str], batch_size: int = None) -> List[List[float]]:
    """批量文本向量化"""
    if batch_size is None:
        batch_size = MAX_DOCUMENT_BATCH_SIZE

    if not texts:
        return []

    _load_model()

    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings = _model.encode(
            batch,
            normalize_embeddings=EMBEDDING_NORMALIZE,
            show_progress_bar=False,
        )
        all_embeddings.extend(embeddings.tolist())

    logger.info(f"批量嵌入完成: {len(texts)}个文本 → {len(all_embeddings)}个向量")
    return all_embeddings


def embed_single(text: str) -> List[float]:
    """单文本向量化"""
    return embed_texts([text])[0]


def embed_query(query: str) -> List[float]:
    """查询向量化（单条，CPU友好）"""
    return embed_single(query)


def load_english_model():
    """加载英文嵌入模型（预留扩展）"""
    global _en_model, _en_model_loaded

    if _en_model_loaded:
        return

    try:
        from sentence_transformers import SentenceTransformer
        logger.info(f"正在加载英文嵌入模型: {EN_EMBEDDING_MODEL_NAME}")
        _en_model = SentenceTransformer(EN_EMBEDDING_MODEL_NAME, device=EMBEDDING_DEVICE)
        _en_model_loaded = True
        logger.info("英文嵌入模型加载完成")
    except Exception as e:
        logger.error(f"英文嵌入模型加载失败: {e}")
        raise


def embed_english_texts(texts: List[str]) -> List[List[float]]:
    """英文文本向量化（预留）"""
    load_english_model()
    embeddings = _en_model.encode(
        texts,
        normalize_embeddings=EMBEDDING_NORMALIZE,
        show_progress_bar=False,
    )
    return embeddings.tolist()


def get_embedding_dimension() -> int:
    """获取当前嵌入模型维度"""
    return VECTOR_DIMENSIONS
