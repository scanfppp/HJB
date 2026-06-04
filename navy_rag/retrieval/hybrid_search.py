"""
混合检索 — 关键词精准检索 + 语义向量检索双模式融合
"""

from typing import List, Dict, Optional

from database.operations import vector_search, keyword_search
from embeddings.embedder import embed_query
from retrieval.reranker import rrf_fusion, apply_status_priority
from utils.logger import get_logger

logger = get_logger(__name__)


def hybrid_search(
    query: str,
    top_k: int = 10,
    filters: Optional[Dict] = None,
    keyword_weight: float = 0.3,
    semantic_weight: float = 0.7,
) -> List[Dict]:
    """
    混合检索主函数
    1. 语义向量检索
    2. 关键词全文检索
    3. RRF融合排序
    4. 文档状态优先级加权
    5. 返回Top-K结果
    """
    if not query.strip():
        return []

    # 第一步：语义向量检索
    logger.info(f"语义检索: {query[:50]}...")
    query_embedding = embed_query(query)
    semantic_results = vector_search(
        embedding=query_embedding,
        top_k=top_k * 2,  # 多取一些用于融合
        filters=filters,
    )

    # 第二步：关键词全文检索
    logger.info(f"关键词检索: {query[:50]}...")
    keyword_results = keyword_search(
        keywords=query,
        top_k=top_k * 2,
        filters=filters,
    )

    # 第三步：RRF融合
    logger.info(f"RRF融合: 语义{len(semantic_results)}条 + 关键词{len(keyword_results)}条")
    fused = rrf_fusion(
        semantic_results=semantic_results,
        keyword_results=keyword_results,
        semantic_k=60,
        keyword_k=60,
        semantic_weight=semantic_weight,
        keyword_weight=keyword_weight,
    )

    # 第四步：文档状态优先级加权
    fused = apply_status_priority(fused)

    # 第五步：截取Top-K
    results = fused[:top_k]

    # 格式化输出
    formatted = []
    for r in results:
        formatted.append({
            "chunk_id": r.get("id"),
            "document_id": r.get("document_id"),
            "chunk_text": r.get("chunk_text", ""),
            "chunk_index": r.get("chunk_index", 0),
            "section_title": r.get("section_title", ""),
            "clause_number": r.get("clause_number", ""),
            "chunk_type": r.get("chunk_type", "指导性说明"),
            "similarity": round(r.get("similarity", 0), 4),
            "standard_number": r.get("standard_number", ""),
            "standard_name": r.get("standard_name", ""),
            "doc_status": r.get("doc_status", ""),
            "applicable_field": r.get("applicable_field", ""),
            "responsible_unit": r.get("responsible_unit", ""),
            "source_ref": f"[{r.get('standard_number', 'N/A')}] {r.get('section_title', '')} {r.get('clause_number', '')}".strip(),
        })

    logger.info(f"混合检索完成: 返回{len(formatted)}条结果")
    return formatted


def search_related_standards(
    standard_field: str,
    exclude_doc_id: Optional[int] = None,
    top_k: int = 10,
) -> List[Dict]:
    """
    检索同领域关联配套标准
    用于查漏补缺功能
    """
    filters = {"applicable_field": standard_field}

    query = f"{standard_field} 标准规范技术要求"

    query_embedding = embed_query(query)
    results = vector_search(
        embedding=query_embedding,
        top_k=top_k * 2,
        filters=filters,
    )

    # 排除当前文档
    if exclude_doc_id is not None:
        results = [r for r in results if r.get("document_id") != exclude_doc_id]

    # 按文档去重，保留每个文档最相关的
    seen_docs = set()
    deduped = []
    for r in results:
        doc_id = r.get("document_id")
        if doc_id not in seen_docs:
            seen_docs.add(doc_id)
            deduped.append(r)
            if len(deduped) >= top_k:
                break

    return deduped
