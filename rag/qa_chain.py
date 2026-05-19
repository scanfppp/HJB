"""
RAG 问答链 — 严格依托入库标准作答，强制标注引用来源
支持多轮上下文连续对话
"""

from typing import List, Dict, Optional, Generator

from config.prompts import RAG_QA_SYSTEM_PROMPT
from retrieval.hybrid_search import hybrid_search
from retrieval.filter import build_search_filters
from llm.client import chat_stream, chat_with_prompt
from database.operations import log_query
from utils.logger import get_logger

logger = get_logger(__name__)


def rag_qa(
    question: str,
    chat_history: Optional[List[Dict]] = None,
    filters: Optional[Dict] = None,
    top_k: int = 10,
    username: str = "",
    stream: bool = False,
):
    """RAG问答主函数"""

    # 第一步：混合检索相关文档片段
    logger.info(f"RAG问答检索: {question[:60]}...")
    search_results = hybrid_search(
        query=question,
        top_k=top_k,
        filters=filters,
    )

    if not search_results:
        response = "根据已入库的海军标准，暂无相关标准依据可回答此问题。建议补充相关标准文档后重新查询。"
        log_query(username, question, response, "问答", [])
        if stream:
            yield response
        else:
            return response, []
        return

    # 第二步：拼接上下文（区分条款类型）
    context_parts = []
    sources = []
    for i, result in enumerate(search_results, 1):
        chunk_type_label = f"【{result.get('chunk_type', '')}】"
        context_parts.append(
            f"[文档{i}] {chunk_type_label}\n"
            f"标准: {result.get('standard_number', 'N/A')} {result.get('standard_name', '')}\n"
            f"章节: {result.get('section_title', '')} {result.get('clause_number', '')}\n"
            f"内容: {result.get('chunk_text', '')}\n"
        )
        sources.append({
            "index": i,
            "standard_number": result.get("standard_number", ""),
            "standard_name": result.get("standard_name", ""),
            "section_title": result.get("section_title", ""),
            "clause_number": result.get("clause_number", ""),
            "chunk_type": result.get("chunk_type", ""),
            "similarity": result.get("similarity", 0),
            "chunk_text": result.get("chunk_text", "")[:200],
        })

    context = "\n---\n".join(context_parts)

    # 第三步：构建提示词
    user_message = f"【用户问题】\n{question}"

    # 如果有多轮历史，拼入
    if chat_history:
        history_text = "\n".join(
            f"{'用户' if h['role'] == 'user' else '助手'}: {h['content']}"
            for h in chat_history[-6:]  # 最近3轮
        )
        user_message = f"【历史对话】\n{history_text}\n\n{user_message}"

    system_prompt = RAG_QA_SYSTEM_PROMPT.format(context=context, question=question)

    # 第四步：调用LLM
    if stream:
        return _stream_response(system_prompt, user_message, username, question, sources)
    else:
        response = chat_with_prompt(system_prompt, user_message)
        log_query(username, question, response, "问答", sources)
        return response, sources


def _stream_response(system_prompt: str, user_message: str,
                     username: str, question: str, sources: list) -> Generator:
    """流式响应生成器"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    full_response = ""
    for chunk in chat_stream(messages):
        full_response += chunk
        yield chunk

    # 记录日志
    log_query(username, question, full_response, "问答", sources)


def multi_turn_qa(
    question: str,
    history: List[Dict],
    filters: Optional[Dict] = None,
    username: str = "",
) -> tuple:
    """多轮对话问答（保留上下文）"""
    return rag_qa(
        question=question,
        chat_history=history,
        filters=filters,
        username=username,
        stream=False,
    )


def format_sources_for_display(sources: list) -> str:
    """格式化引用来源用于前端展示"""
    if not sources:
        return "暂无引用来源"

    lines = []
    for s in sources:
        lines.append(
            f"- **[{s['standard_number']}]** {s['standard_name']} "
            f"> {s['section_title']} {s['clause_number']} "
            f"({s['chunk_type']}, 相似度: {s['similarity']:.2f})"
        )
    return "\n".join(lines)
