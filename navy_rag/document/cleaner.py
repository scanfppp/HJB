"""
文本清洗器 — 页眉页脚剔除、文本降噪、去冗余排版
适配军用标准文档特征
"""

import re
from utils.logger import get_logger

logger = get_logger(__name__)


def clean_text(text: str) -> str:
    """主清洗流程：依次执行各清洗步骤"""
    if not text:
        return ""

    text = remove_headers_footers(text)
    text = remove_page_numbers(text)
    text = normalize_whitespace(text)
    text = remove_noise_patterns(text)
    text = normalize_punctuation(text)
    text = remove_short_lines(text)

    logger.info(f"文本清洗完成，长度: {len(text)} 字符")
    return text.strip()


def remove_headers_footers(text: str) -> str:
    """检测并剔除页眉页脚（基于重复模式识别）
    策略：识别每页重复出现的相同或相似行
    """
    lines = text.split("\n")
    if len(lines) < 3:
        return text

    # 统计每行出现的次数（模糊匹配）
    line_counts = {}
    for line in lines:
        stripped = line.strip()
        if len(stripped) > 5:
            line_counts[stripped] = line_counts.get(stripped, 0) + 1

    # 出现超过总页数30%的行视为页眉页脚候选
    page_estimate = max(len(lines) // 40, 1)
    threshold = max(page_estimate * 0.3, 2)

    header_footer_candidates = {
        line for line, count in line_counts.items()
        if count >= threshold and len(line) < 100
    }

    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped not in header_footer_candidates:
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def remove_page_numbers(text: str) -> str:
    """移除独立页码行"""
    patterns = [
        r'^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$',  # 纯数字页码
        r'^\s*第\s*\d+\s*页\s*(共\s*\d+\s*页)?\s*$',  # "第X页" / "第X页 共Y页"
        r'^\s*page\s*\d+\s*(of\s*\d+)?\s*$',  # 英文页码
    ]

    lines = text.split("\n")
    cleaned = []
    for line in lines:
        is_page_num = False
        for pat in patterns:
            if re.match(pat, line, re.IGNORECASE):
                is_page_num = True
                break
        if not is_page_num:
            cleaned.append(line)

    return "\n".join(cleaned)


def normalize_whitespace(text: str) -> str:
    """规范化空白字符"""
    # 统一换行符
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 压缩多个连续空行为单个空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 去除行首行尾空白
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines)


def remove_noise_patterns(text: str) -> str:
    """移除常见文档噪声"""
    patterns = [
        # 水印标记
        r'内部资料[，,\s]*注意保密',
        r'密级[：:]\s*\S+',
        r'版权所有\s*\S*',
        # URL链接
        r'https?://\S+',
        # 长串特殊字符（分隔线等）
        r'^[\*\-=_\s]{10,}$',
        # 文件路径
        r'[A-Za-z]:\\[\w\\]+\.\w+',
        # 批量删除重复的标点序列
        r'[。，、；：]{5,}',
    ]

    for pat in patterns:
        text = re.sub(pat, '', text, flags=re.MULTILINE)

    return text


def normalize_punctuation(text: str) -> str:
    """统一标点符号（中文标点标准化）"""
    replacements = {
        '﹐': '，', '﹔': '；', '﹕': '：', '﹖': '？', '﹗': '！',
        '﹐': '，', '、': '、',
        '（': '（', '）': '）',
        '［': '[', '］': ']',
        '｛': '{', '｝': '}',
        '　': ' ',  # 全角空格
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # 中英文之间的空格处理
    text = re.sub(r'([a-zA-Z0-9])([一-鿿])', r'\1 \2', text)
    text = re.sub(r'([一-鿿])([a-zA-Z0-9])', r'\1 \2', text)

    return text


def remove_short_lines(text: str, min_len: int = 3) -> str:
    """移除过短的非内容行（如单独标点、单独数字等）"""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # 保留标题类短行（以#开头或以序号开头）
        if len(stripped) < min_len and not (
            stripped.startswith("#") or
            re.match(r'^[\d一二三四五六七八九十]+[、.．]', stripped) or
            stripped.startswith("第")
        ):
            # 检查是否纯数字或纯标点
            if re.match(r'^[\d\s\.,;:!?，。；：！？…\-\—]+$', stripped):
                continue
        cleaned.append(line)
    return "\n".join(cleaned)
