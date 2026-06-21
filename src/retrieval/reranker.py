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


def _trigram_jaccard(text1: str, text2: str) -> float:
    """计算两段文本的 trigram Jaccard 相似度"""
    if not text1 or not text2:
        return 0.0

    def trigrams(text):
        return {text[i:i + 3] for i in range(len(text) - 2)}

    t1 = trigrams(text1)
    t2 = trigrams(text2)
    if not t1 or not t2:
        return 0.0
    return len(t1 & t2) / len(t1 | t2)


def deduplicate_similar_chunks(results: List[Dict],
                                threshold: float = 0.6) -> List[Dict]:
    """
    去重近似重复的 chunk（含同文档相邻 + 跨文档重复）。
    对所有结果按 fusion_score 降序排列，逐个与已保留条目比较，
    若 trigram Jaccard > threshold 则跳过。
    """
    if not results:
        return results

    # 按分数降序，优先保留高分条目
    sorted_results = sorted(
        enumerate(results),
        key=lambda x: x[1].get("fusion_score", 0),
        reverse=True,
    )

    kept = []
    to_remove = set()

    for idx, item in sorted_results:
        text = item.get("chunk_text", "")
        is_dup = False
        for kept_item in kept:
            sim = _trigram_jaccard(text, kept_item.get("chunk_text", ""))
            if sim > threshold:
                is_dup = True
                break
        if is_dup:
            to_remove.add(idx)
        else:
            kept.append(item)

    if not to_remove:
        return results

    filtered = [r for i, r in enumerate(results) if i not in to_remove]
    logger.info(f"近似去重: {len(results)}条 → {len(filtered)}条 "
                f"(移除{len(to_remove)}条近似重复)")
    return filtered


def filter_low_quality(results: List[Dict],
                       min_score: float = 0.005) -> List[Dict]:
    """
    过滤低相关度结果。
    保留 fusion_score >= min_score 的条目。
    兜底：若过滤后为空，返回原始结果。
    """
    if not results:
        return results

    filtered = [r for r in results if r.get("fusion_score", 0) >= min_score]

    if not filtered:
        logger.info(f"低质过滤: 全部{len(results)}条不达标(min={min_score})，保留原始结果")
        return results

    removed = len(results) - len(filtered)
    if removed > 0:
        logger.info(f"低质过滤: {len(results)}条 → {len(filtered)}条 "
                    f"(移除{removed}条, 阈值={min_score})")
    return filtered
