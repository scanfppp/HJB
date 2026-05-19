"""
工具函数集合
"""

import os
import re
import json
from datetime import datetime, date
from typing import Any


def safe_json_dumps(obj: Any, default_str: str = "{}") -> str:
    """安全的JSON序列化"""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return default_str


def safe_json_loads(s: str, default: Any = None) -> Any:
    """安全的JSON反序列化"""
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return default


def truncate_text(text: str, max_len: int = 200, suffix: str = "...") -> str:
    """截断文本"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + suffix


def format_date(d: Any) -> str:
    """格式化日期"""
    if d is None:
        return ""
    if isinstance(d, datetime):
        return d.strftime("%Y-%m-%d %H:%M")
    if isinstance(d, date):
        return d.strftime("%Y-%m-%d")
    if isinstance(d, str):
        return d[:10]
    return str(d)


def extract_chinese_text(text: str) -> str:
    """提取纯中文文本"""
    chinese_chars = re.findall(r'[一-鿿　-〿＀-￯]', text)
    return ''.join(chinese_chars)


def count_tokens_approx(text: str) -> int:
    """粗略估算Token数量（中文约1.5字符/Token）"""
    chinese_count = len(re.findall(r'[一-鿿]', text))
    other_count = len(text) - chinese_count
    return int(chinese_count * 0.7 + other_count * 0.25)


def get_file_type_icon(file_type: str) -> str:
    """获取文件类型图标"""
    icons = {
        "pdf": "📄",
        "docx": "📝",
        "txt": "📃",
    }
    return icons.get(file_type.lower(), "📎")


def generate_id() -> str:
    """生成唯一ID"""
    import uuid
    return uuid.uuid4().hex[:12]


def ensure_dir(path: str):
    """确保目录存在"""
    os.makedirs(path, exist_ok=True)
