"""
标准查漏补缺 & 内容升级优化 — 核心高阶功能
自动识别内容缺口、给出增补建议、草拟修订初稿
"""

from typing import Dict, List, Optional

from config.prompts import (
    GAP_ANALYSIS_PROMPT,
    STANDARD_COMPARE_PROMPT,
    DRAFT_REVISION_PROMPT,
)
from database.operations import get_document, get_chunks_by_document, list_documents
from retrieval.hybrid_search import search_related_standards, hybrid_search
from llm.client import chat_with_prompt
from utils.logger import get_logger

logger = get_logger(__name__)


def analyze_text(text: str, standard_name: str = "") -> Dict:
    """
    标准分析函数（基于任意文本，无需入库）
    """
    # 用文本内容检索关联标准
    from retrieval.hybrid_search import hybrid_search
    search_results = hybrid_search(query=text if not standard_name else standard_name, top_k=10)

    related_docs = []
    context_parts = []
    for r in search_results:
        related_docs.append({
            "standard_number": r.get("standard_number", ""),
            "standard_name": r.get("standard_name", ""),
            "doc_status": r.get("doc_status", ""),
            "similarity": r.get("similarity", 0),
        })
        context_parts.append(
            f"【{r.get('standard_number', '')} {r.get('standard_name', '')}】\n"
            f"内容: {r.get('chunk_text', '')[:1000]}\n"
        )

    related_content = "\n---\n".join(context_parts) if context_parts else "暂无关联标准"
    name = standard_name or "用户提交内容"

    prompt = GAP_ANALYSIS_PROMPT.format(
        standard_number="",
        standard_name=name,
        applicable_field="",
        target_content=text[:8000],
        related_content=related_content[:8000],
    )

    gap_report = chat_with_prompt(
        prompt,
        f"请对《{name}》进行标准化分析",
        max_tokens=4096,
    )

    return {
        "gap_report": gap_report,
        "related_standards": related_docs,
    }


def analyze_gaps(
    doc_id: int,
    include_draft: bool = False,
) -> Dict:
    """
    标准查漏补缺主分析函数

    步骤：
    1. 获取目标标准全部内容
    2. 自动检索同领域关联配套标准
    3. LLM对比分析识别缺口
    4. （可选）生成修订初稿
    """
    # 步骤1：获取目标标准
    doc_info = get_document(doc_id)
    if not doc_info:
        return {"error": "目标标准不存在"}

    chunks = get_chunks_by_document(doc_id)
    if not chunks:
        return {"error": "目标标准无已分块内容"}

    # 拼接目标标准完整内容
    target_content = _build_content_from_chunks(chunks)
    standard_number = doc_info.get("standard_number", "")
    standard_name = doc_info.get("standard_name", "")
    applicable_field = doc_info.get("applicable_field", "")

    logger.info(f"开始查漏补缺分析: {standard_number} {standard_name}")

    # 步骤2：检索关联配套标准
    related_results = search_related_standards(
        standard_field=applicable_field,
        exclude_doc_id=doc_id,
        top_k=10,
    )

    # 构建关联标准内容
    related_content_parts = []
    related_docs_summary = []
    for r in related_results:
        related_content_parts.append(
            f"【{r.get('standard_number', '')} {r.get('standard_name', '')}】\n"
            f"关联内容: {r.get('chunk_text', '')[:1000]}\n"
        )
        related_docs_summary.append({
            "standard_number": r.get("standard_number", ""),
            "standard_name": r.get("standard_name", ""),
            "doc_status": r.get("doc_status", ""),
            "similarity": r.get("similarity", 0),
        })

    related_content = "\n---\n".join(related_content_parts) if related_content_parts else "暂无关联标准数据"

    # 步骤3：LLM分析
    gap_prompt = GAP_ANALYSIS_PROMPT.format(
        standard_number=standard_number,
        standard_name=standard_name,
        applicable_field=applicable_field,
        target_content=target_content[:10000],
        related_content=related_content[:8000],
    )

    gap_report = chat_with_prompt(
        gap_prompt,
        f"请对标准《{standard_number} {standard_name}》进行查漏补缺分析",
        max_tokens=4096,
    )

    result = {
        "doc_id": doc_id,
        "standard_number": standard_number,
        "standard_name": standard_name,
        "applicable_field": applicable_field,
        "gap_report": gap_report,
        "related_standards": related_docs_summary,
        "related_count": len(related_docs_summary),
    }

    # 步骤4（可选）：生成修订初稿
    if include_draft:
        draft = generate_revision_draft(
            current_content=target_content,
            gap_analysis=gap_report,
        )
        result["revision_draft"] = draft

    logger.info(f"查漏补缺分析完成: {standard_number}")
    return result


def compare_standards(doc_id_old: int, doc_id_new: int) -> Dict:
    """新旧版本标准差异对比"""
    old_info = get_document(doc_id_old)
    new_info = get_document(doc_id_new)

    if not old_info or not new_info:
        return {"error": "标准文档不存在"}

    old_chunks = get_chunks_by_document(doc_id_old)
    new_chunks = get_chunks_by_document(doc_id_new)

    old_content = _build_content_from_chunks(old_chunks)
    new_content = _build_content_from_chunks(new_chunks)

    compare_prompt = STANDARD_COMPARE_PROMPT.format(
        old_content=old_content[:8000],
        new_content=new_content[:8000],
    )

    title = f"{old_info.get('standard_number', '')} v.s. {new_info.get('standard_number', '')}"
    report = chat_with_prompt(
        compare_prompt,
        f"请对比分析以下两个版本的标准：{title}",
        max_tokens=4096,
    )

    return {
        "old_standard": {
            "id": doc_id_old,
            "number": old_info.get("standard_number", ""),
            "name": old_info.get("standard_name", ""),
        },
        "new_standard": {
            "id": doc_id_new,
            "number": new_info.get("standard_number", ""),
            "name": new_info.get("standard_name", ""),
        },
        "comparison_report": report,
    }


def generate_revision_draft(current_content: str, gap_analysis: str) -> str:
    """基于缺口分析草拟标准修订初稿"""
    draft_prompt = DRAFT_REVISION_PROMPT.format(
        current_content=current_content[:8000],
        gap_analysis=gap_analysis[:4000],
    )

    draft = chat_with_prompt(
        draft_prompt,
        "请基于以上缺口分析，草拟标准修订初稿",
        max_tokens=4096,
    )

    return draft


def _build_content_from_chunks(chunks: list) -> str:
    """将chunks拼接为完整文档内容"""
    parts = []
    for c in chunks:
        section = c.get("section_title", "")
        clause = c.get("clause_number", "")
        header = f"{section} {clause}".strip()
        if header:
            parts.append(f"## {header}\n{c.get('chunk_text', '')}")
        else:
            parts.append(c.get("chunk_text", ""))
    return "\n\n".join(parts)


def get_available_standards() -> List[Dict]:
    """获取可用于对比分析的标准列表"""
    return list_documents(is_active=True, limit=200)
