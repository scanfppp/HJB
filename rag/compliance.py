"""
合规自查 — 用户提交制度/方案对照标准校验合规性
支持流式输出和合规评分看板
"""

import json, re
from typing import Dict, Optional, List, Tuple

from config.prompts import COMPLIANCE_CHECK_PROMPT
from retrieval.hybrid_search import hybrid_search
from llm.client import chat_with_prompt
from utils.logger import get_logger

logger = get_logger(__name__)


def build_compliance_messages(submitted_text: str, search_results: list) -> list:
    """构建合规检查的 messages 列表，供流式端点使用"""
    standards_text_parts = []
    for i, r in enumerate(search_results, 1):
        standards_text_parts.append(
            f"[标准{i}] {r.get('standard_number', '')} {r.get('standard_name', '')}\n"
            f"章节: {r.get('section_title', '')} {r.get('clause_number', '')}\n"
            f"条款类型: {r.get('chunk_type', '')}\n"
            f"内容: {r.get('chunk_text', '')}\n"
        )

    relevant_standards = "\n---\n".join(standards_text_parts)
    truncated = len(submitted_text) > 6000 or len(relevant_standards) > 6000
    if truncated:
        logger.warning(f"合规自查: 文本被截断 (原文{len(submitted_text)}字/标准{len(relevant_standards)}字)")

    prompt = COMPLIANCE_CHECK_PROMPT.format(
        submitted_text=submitted_text[:6000],
        relevant_standards=relevant_standards[:6000],
    )
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "请对提交的制度/方案进行合规性校验"},
    ]


def build_compliance_sources(search_results: list) -> list:
    """从检索结果构建来源列表"""
    return [
        {
            "index": i,
            "standard_number": r.get("standard_number", ""),
            "standard_name": r.get("standard_name", ""),
            "section_title": r.get("section_title", ""),
            "clause_number": r.get("clause_number", ""),
            "chunk_type": r.get("chunk_type", ""),
        }
        for i, r in enumerate(search_results, 1)
    ]


def parse_compliance_score(report: str) -> dict:
    """从合规报告末尾解析 JSON 评分块"""
    try:
        matches = re.findall(r'\{[^}]*"total"[^}]*\}', report)
        if matches:
            return json.loads(matches[-1])
    except (json.JSONDecodeError, KeyError):
        pass

    # Fallback: 统计报告中符合/不符合关键词
    compliant = len(re.findall(r'\|\s*符合\s*\|', report))
    partial = len(re.findall(r'\|\s*部分符合\s*\|', report))
    non_compliant = len(re.findall(r'\|\s*不符合\s*\|', report))
    total = compliant + partial + non_compliant
    if total > 0:
        return {
            "total": total,
            "compliant": compliant,
            "partial": partial,
            "non_compliant": non_compliant,
            "percentage": round(compliant / total * 100, 1),
        }
    return {}


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
