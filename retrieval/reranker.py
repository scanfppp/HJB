"""
结果重排序 — RRF 融合 + 文档状态优先级加权
"""

from typing import List, Dict
from config.settings import STATUS_PRIORITY
from utils.logger import get_logger

logger = get_logger(__name__)


def rrf_fusion(
    semantic_results: List[Dict],
    keyword_results: List[Dict],
    semantic_k: int = 60,
    keyword_k: int = 60,
    semantic_weight: float = 0.7,
    keyword_weight: float = 0.3,
) -> List[Dict]:
    """
    Reciprocal Rank Fusion (RRF) 融合算法
    合并语义检索和关键词检索两路结果
    """

    # 使用 chunk_id 或 (document_id, chunk_index) 作为唯一标识
    def _key(item):
        return f"{item.get('document_id')}_{item.get('chunk_index')}_{item.get('id')}"

    scores = {}
    items_map = {}

    # 语义检索评分
    for rank, item in enumerate(semantic_results):
        k = _key(item)
        rrf_score = semantic_weight / (semantic_k + rank + 1)
        scores[k] = scores.get(k, 0) + rrf_score
        # 同时累加余弦相似度
        scores[k] += item.get("similarity", 0) * semantic_weight
        items_map[k] = item

    # 关键词检索评分
    for rank, item in enumerate(keyword_results):
        k = _key(item)
        rrf_score = keyword_weight / (keyword_k + rank + 1)
        scores[k] = scores.get(k, 0) + rrf_score
        # 只保留最完整的信息
        if k not in items_map or len(item.get("chunk_text", "")) > len(items_map[k].get("chunk_text", "")):
            items_map[k] = item

    # 按融合分数排序
    sorted_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)

    result = []
    for k in sorted_keys:
        item = items_map[k]
        item["fusion_score"] = round(scores[k], 6)
        item["similarity"] = round(scores[k] / (semantic_weight + keyword_weight + 1), 4)
        result.append(item)

    logger.info(f"RRF融合: {len(semantic_results)}条语义 + {len(keyword_results)}条关键词 → {len(result)}条融合结果")
    return result


def apply_status_priority(results: List[Dict]) -> List[Dict]:
    """
    按文档状态施加优先级加权
    现行有效 > 修订中 > 废止
    """
    if not results:
        return results

    for item in results:
        status = item.get("doc_status", "")
        priority = STATUS_PRIORITY.get(status, 0.5)
        # 将优先级因子乘入融合分数
        item["fusion_score"] = item.get("fusion_score", 0) * priority
        item["priority_boost"] = priority

    # 重新排序
    results.sort(key=lambda x: x.get("fusion_score", 0), reverse=True)
    return results


def deduplicate_by_document(results: List[Dict]) -> List[Dict]:
    """按文档去重，每个文档只保留最相关的一条"""
    seen = set()
    deduped = []
    for r in results:
        doc_id = r.get("document_id")
        if doc_id not in seen:
            seen.add(doc_id)
            deduped.append(r)
    return deduped
