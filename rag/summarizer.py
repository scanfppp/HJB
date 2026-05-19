"""
长文档智能总结 — Map-Reduce 结构化提炼
输出精简版总结 + 完整版要点清单双格式
"""

from typing import List, Dict

from config.prompts import SUMMARIZE_MAP_PROMPT, SUMMARIZE_REDUCE_PROMPT
from database.operations import get_chunks_by_document, get_document
from llm.client import chat_with_prompt
from utils.logger import get_logger

logger = get_logger(__name__)


def summarize_document(
    doc_id: int,
    detail_level: str = "full",  # "brief" 或 "full"
) -> Dict:
    """
    对指定文档进行结构化总结
    返回包含精简版和完整版的字典
    """
    # 获取文档信息和所有chunks
    doc_info = get_document(doc_id)
    if not doc_info:
        return {"error": "文档不存在或已被删除"}

    chunks = get_chunks_by_document(doc_id)
    if not chunks:
        return {"error": "文档没有已分块内容，请先完成文档解析入库"}

    logger.info(f"开始总结文档 {doc_id}: {doc_info.get('standard_name', '')}, {len(chunks)}个块")

    # Map阶段：每个chunk提取要点
    map_results = []
    for chunk in chunks[:30]:  # 限制处理的块数，避免Token溢出
        chunk_text = chunk["chunk_text"]
        if len(chunk_text) < 50:
            continue

        section_label = f"{chunk.get('section_title', '')} {chunk.get('clause_number', '')}".strip()
        prompt = SUMMARIZE_MAP_PROMPT.format(chunk_text=chunk_text)
        try:
            summary = chat_with_prompt(prompt, f"请提炼以下章节要点（{section_label}）")
            map_results.append({
                "section": section_label or "正文",
                "chunk_type": chunk.get("chunk_type", ""),
                "summary": summary,
            })
        except Exception as e:
            logger.warning(f"Map阶段处理失败: {e}")
            map_results.append({
                "section": section_label or "正文",
                "chunk_type": chunk.get("chunk_type", ""),
                "summary": chunk_text[:300] + "...",
            })

    # Reduce阶段：汇总提炼
    map_text = "\n\n---\n\n".join(
        f"【{m['section']}】({m['chunk_type']})\n{m['summary']}"
        for m in map_results
    )

    reduce_prompt = SUMMARIZE_REDUCE_PROMPT.format(map_results=map_text)
    doc_title = f"{doc_info.get('standard_number', '')} {doc_info.get('standard_name', '')}"
    final_summary = chat_with_prompt(
        reduce_prompt,
        f"请基于以上要点汇总，输出标准文档《{doc_title}》的结构化总结。",
        max_tokens=4096,
    )

    # 提取精简版（从完整版中截取第一部分）
    brief_summary = ""
    if "## 一、精简版总结" in final_summary:
        parts = final_summary.split("## 二、完整版要点清单")
        if len(parts) >= 1:
            brief_summary = parts[0].replace("## 一、精简版总结", "").strip()
            # 限制500字
            if len(brief_summary) > 500:
                brief_summary = brief_summary[:500] + "..."

    if detail_level == "brief":
        result_text = brief_summary or final_summary[:500]
    else:
        result_text = final_summary

    logger.info(f"文档总结完成: {doc_id}")

    return {
        "doc_id": doc_id,
        "standard_number": doc_info.get("standard_number", ""),
        "standard_name": doc_info.get("standard_name", ""),
        "brief_summary": brief_summary or final_summary[:500],
        "full_summary": final_summary,
        "detail_level": detail_level,
        "chunks_processed": len(map_results),
        "total_chunks": len(chunks),
    }


def summarize_text(text: str, title: str = "") -> str:
    """快速总结任意文本（非入库文档）"""
    if len(text) < 100:
        return text

    prompt = SUMMARIZE_REDUCE_PROMPT.format(
        map_results=text[:8000]  # 限制输入长度
    )
    summary = chat_with_prompt(
        prompt,
        f"请总结以下文档内容：{title}",
        max_tokens=2048,
    )
    return summary
