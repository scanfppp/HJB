"""
合规自查 — 用户提交制度/方案对照标准校验合规性
"""

from typing import Dict, Optional

from config.prompts import COMPLIANCE_CHECK_PROMPT
from retrieval.hybrid_search import hybrid_search
from llm.client import chat_with_prompt
from utils.logger import get_logger

logger = get_logger(__name__)


def check_compliance(
    submitted_text: str,
    applicable_field: Optional[str] = None,
) -> Dict:
    """
    合规自查主函数

    步骤：
    1. 检索相关标准条款
    2. 对照标准逐条校验
    3. 输出合规报告
    """
    if not submitted_text.strip():
        return {"error": "请输入需要校验的制度/方案内容"}

    logger.info(f"开始合规自查: 文本{len(submitted_text)}字")

    # 步骤1：检索相关标准
    filters = None
    if applicable_field and applicable_field.strip():
        filters = {"applicable_field": applicable_field.strip()}

    # 用提交文本的关键部分作为检索query
    query = submitted_text[:500]
    search_results = hybrid_search(
        query=query,
        top_k=10,
        filters=filters,
    )

    if not search_results:
        return {
            "submitted_text": submitted_text,
            "report": "未能检索到相关的海军标准条款，无法进行合规校验。请确认已入库相关领域的标准文档。",
            "sources": [],
        }

    # 步骤2：构建标准条款内容
    standards_text_parts = []
    sources = []
    for i, r in enumerate(search_results, 1):
        standards_text_parts.append(
            f"[标准{i}] {r.get('standard_number', '')} {r.get('standard_name', '')}\n"
            f"章节: {r.get('section_title', '')} {r.get('clause_number', '')}\n"
            f"条款类型: {r.get('chunk_type', '')}\n"
            f"内容: {r.get('chunk_text', '')}\n"
        )
        sources.append({
            "index": i,
            "standard_number": r.get("standard_number", ""),
            "standard_name": r.get("standard_name", ""),
            "section_title": r.get("section_title", ""),
            "clause_number": r.get("clause_number", ""),
            "chunk_type": r.get("chunk_type", ""),
        })

    relevant_standards = "\n---\n".join(standards_text_parts)

    # 步骤3：LLM合规分析
    compliance_prompt = COMPLIANCE_CHECK_PROMPT.format(
        submitted_text=submitted_text[:6000],
        relevant_standards=relevant_standards[:6000],
    )

    report = chat_with_prompt(
        compliance_prompt,
        "请对提交的制度/方案进行合规性校验",
        max_tokens=4096,
    )

    logger.info("合规自查完成")

    return {
        "submitted_text": submitted_text,
        "report": report,
        "sources": sources,
        "standards_count": len(search_results),
    }
