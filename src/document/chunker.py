"""
文本分块器 — 按章节、条款精细化分块
保留上下文关联，适配768维向量入库
"""

import re
from typing import List, Dict
from config.settings import CHUNK_SIZE, CHUNK_OVERLAP
from utils.logger import get_logger

logger = get_logger(__name__)


def chunk_text(text: str) -> List[Dict]:
    """主分块函数：识别章节层级 → 按条款分块 → 合并小块"""
    if not text:
        return []

    # 第一步：按章节层级切分
    sections = split_by_sections(text)

    # 第二步：在每个章节内按条款细分
    chunks = []
    for section in sections:
        sub_chunks = split_by_clauses(section["content"], section["title"])
        for sc in sub_chunks:
            chunks.append({
                "section_title": section["title"],
                "section_level": section["level"],
                "chunk_text": sc["text"],
                "clause_number": sc.get("clause_number", ""),
                "chunk_type": detect_chunk_type(sc["text"]),
            })

    # 第三步：合并过小的块，拆分过大的块
    chunks = merge_small_chunks(chunks)
    chunks = split_large_chunks(chunks)

    # 添加序号
    for i, chunk in enumerate(chunks):
        chunk["chunk_index"] = i

    logger.info(f"文本分块完成: {len(chunks)}个块")
    return chunks


def split_by_sections(text: str) -> List[Dict]:
    """按章节标题切分"""
    # 匹配中文章节标题模式
    patterns = [
        (1, r'第[一二三四五六七八九十百千]+篇\s*.+'),      # 第X篇
        (1, r'第[一二三四五六七八九十百千]+章\s*.+'),      # 第X章
        (1, r'第\d+章\s*.+'),                               # 第1章
        (2, r'第[一二三四五六七八九十百千]+节\s*.+'),      # 第X节
        (2, r'第\d+节\s*.+'),                               # 第1节
        (3, r'[一二三四五六七八九十]+[、.．]\s*.+'),       # 一、XXX
        (3, r'\d+[.、．]\s*.+'),                             # 1. XXX
    ]

    # 构建完整匹配模式
    full_pattern = '|'.join(f'(?:{p[1]})' for p in patterns)

    lines = text.split('\n')
    sections = []
    current_title = "正文"
    current_level = 0
    current_lines = []

    for line in lines:
        stripped = line.strip()
        matched = False
        for level, pat in patterns:
            m = re.match(pat, stripped)
            if m:
                # 保存上一个section
                if current_lines:
                    sections.append({
                        "title": current_title,
                        "level": current_level,
                        "content": "\n".join(current_lines),
                    })
                current_title = stripped
                current_level = level
                current_lines = []
                matched = True
                break

        if not matched:
            current_lines.append(line)

    # 最后一个section
    if current_lines:
        sections.append({
            "title": current_title,
            "level": current_level,
            "content": "\n".join(current_lines),
        })

    logger.info(f"章节切分: {len(sections)}个章节")
    return sections


def split_by_clauses(content: str, section_title: str) -> List[Dict]:
    """在章节内按条款进一步细分"""
    # 匹配条款编号模式
    clause_patterns = [
        r'第[一二三四五六七八九十百千\d]+条\s*',    # 第X条
        r'\d+\.\d+\s+',                                # 1.1
        r'[（(]\d+[）)]\s*',                             # (1) （1）
        r'^\d+[、.．]\s*',                              # 1、 1.
    ]

    # 按段落自然分割
    paragraphs = content.split('\n')
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if len(paragraphs) <= 1:
        return [{"text": content, "clause_number": ""}]

    clauses = []
    current_clause = ""
    current_number = ""

    for para in paragraphs:
        is_new = False
        for pat in clause_patterns:
            m = re.match(pat, para)
            if m:
                if current_clause:
                    clauses.append({
                        "text": current_clause.strip(),
                        "clause_number": current_number,
                    })
                current_number = m.group().strip()
                current_clause = para
                is_new = True
                break

        if not is_new:
            current_clause += "\n" + para if current_clause else para

    if current_clause:
        clauses.append({
            "text": current_clause.strip(),
            "clause_number": current_number,
        })

    return clauses


def detect_chunk_type(text: str) -> str:
    """自动识别块类型：强制执行/推荐执行/指导性说明"""
    mandatory_keywords = ["必须", "严禁", "禁止", "不得", "应当", "不得", "强制执行"]
    recommend_keywords = ["宜", "建议", "推荐", "最好", "可参照"]
    guide_keywords = ["说明", "注：", "注:", "例如", "示例", "指导"]

    text_lower = text.lower()

    mandatory_score = sum(1 for kw in mandatory_keywords if kw in text)
    recommend_score = sum(1 for kw in recommend_keywords if kw in text)
    guide_score = sum(1 for kw in guide_keywords if kw in text_lower)

    if mandatory_score > recommend_score and mandatory_score > guide_score:
        return "强制执行条款"
    elif recommend_score > mandatory_score and recommend_score > guide_score:
        return "推荐执行条款"
    else:
        return "指导性说明条款"


def merge_small_chunks(chunks: List[Dict], min_size: int = 200) -> List[Dict]:
    """合并过小的块到相邻块"""
    if len(chunks) <= 1:
        return chunks

    merged = []
    buffer = None

    for chunk in chunks:
        if len(chunk["chunk_text"]) < min_size:
            if buffer is None:
                buffer = chunk
            else:
                # 合并到buffer
                buffer["chunk_text"] += "\n" + chunk["chunk_text"]
                if chunk["clause_number"]:
                    buffer["clause_number"] += f", {chunk['clause_number']}"
        else:
            if buffer:
                # 将buffer合并到当前chunk
                chunk["chunk_text"] = buffer["chunk_text"] + "\n" + chunk["chunk_text"]
                if buffer["clause_number"]:
                    chunk["clause_number"] = f"{buffer['clause_number']}, {chunk['clause_number']}"
                buffer = None
            merged.append(chunk)

    if buffer:
        if merged:
            merged[-1]["chunk_text"] += "\n" + buffer["chunk_text"]
        else:
            merged.append(buffer)

    return merged


def split_large_chunks(chunks: List[Dict], max_size: int = None) -> List[Dict]:
    """拆分过大的块"""
    if max_size is None:
        max_size = CHUNK_SIZE + CHUNK_OVERLAP

    result = []
    for chunk in chunks:
        text = chunk["chunk_text"]
        if len(text) <= max_size:
            result.append(chunk)
            continue

        # 按句子边界拆分
        sentences = re.split(r'(?<=[。！？\.!\?])\s*', text)
        current_text = ""
        for sent in sentences:
            if len(current_text) + len(sent) > max_size and current_text:
                result.append({
                    "section_title": chunk["section_title"],
                    "section_level": chunk["section_level"],
                    "chunk_text": current_text.strip(),
                    "clause_number": chunk["clause_number"],
                    "chunk_type": chunk["chunk_type"],
                })
                # 重叠前一个块的最后部分
                overlap_text = current_text[-CHUNK_OVERLAP:] if len(current_text) > CHUNK_OVERLAP else current_text
                current_text = overlap_text + sent
            else:
                current_text += sent

        if current_text.strip():
            result.append({
                "section_title": chunk["section_title"],
                "section_level": chunk["section_level"],
                "chunk_text": current_text.strip(),
                "clause_number": chunk["clause_number"],
                "chunk_type": chunk["chunk_type"],
            })

    return result
