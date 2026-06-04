"""
元数据提取与校验 — 入库必填标签字段
支持自动提取和手动录入
"""

import re
from typing import Optional
from datetime import date, datetime
from utils.logger import get_logger

logger = get_logger(__name__)

REQUIRED_FIELDS = [
    "standard_number",   # 标准编号
    "standard_name",     # 标准名称
    "applicable_field",  # 适用领域
    "publish_date",      # 发布时间
    "implement_date",    # 实施时间
    "doc_status",        # 文档状态
    "responsible_unit",  # 归口单位
]

VALID_STATUSES = ["现行有效", "废止", "修订中"]


def extract_metadata_from_text(text: str, file_name: str = "") -> dict:
    """从文本中自动提取标准元数据，优先从文档头部匹配"""
    metadata = {
        "standard_number": "",
        "standard_name": "",
        "applicable_field": "",
        "publish_date": None,
        "implement_date": None,
        "doc_status": "现行有效",
        "responsible_unit": "",
    }

    # 取文档头部（前800字），标准编号和名称通常在这里
    header = text[:800]
    # 清理：去掉"中国人民解放军海军标准"等前缀干扰
    header_clean = re.sub(r'中国人民解放军海军标准\s*', '', header)

    # 1. 从文档头部提取标准编号
    #    格式: HJB 590B-2025, GJB 4072B-2023 等
    #    优先匹配紧跟标题文字的编号（行首或紧接中文前）
    number = _extract_standard_number_from_header(header_clean)
    if not number:
        number = _extract_standard_number_from_header(text[:1500])
    metadata["standard_number"] = number

    # 2. 从文档头部提取标准名称
    #    通常在编号后面：HJB 590B-2025 舰船舰载软件质量监督通用要求
    #    或者是单独一行的大标题
    metadata["standard_name"] = _extract_standard_name(text, header_clean, metadata["standard_number"])

    # 3. 从文件名补充
    if not metadata["standard_name"] and file_name:
        base = file_name.rsplit(".", 1)[0]
        # 去掉可能的时间戳前缀
        base = re.sub(r'^\d+_', '', base)
        if len(base) >= 5:
            metadata["standard_name"] = base
    if not metadata["standard_number"] and file_name:
        num_match = re.search(r'([A-Z]+\s*\d+[A-Z]?[\.\-]?\d*)', file_name)
        if num_match:
            metadata["standard_number"] = num_match.group(1)

    # 4. 提取日期（从头部优先）
    metadata["publish_date"], metadata["implement_date"] = _extract_dates(text[:3000])

    # 5. 提取归口单位
    metadata["responsible_unit"] = _extract_responsible_unit(text[:2000])

    return metadata


def _extract_standard_number_from_header(header: str) -> str:
    """从文档头部提取标准编号，只匹配头部避免前言中的引用干扰"""
    patterns = [
        # HJB 590B-2025 或 HJB 590B—2025（中文破折号）
        r'(HJB\s*\d+[A-Za-z]?\s*[—\-–]\s*\d{4})',
        # GJB 4072B-2023
        r'(GJB\s*\d+[A-Za-z]?\s*[—\-–]\s*\d{4})',
        # CB xxx-xxxx, GB/T xxx-xxxx 等
        r'([A-Z]{2,5}(?:/[A-Z])?\s*\d+[A-Za-z]?\s*[—\-–]\s*\d{2,4})',
        # 纯编号形式: Q/JB xxx-xxxx
        r'([A-Z]/[A-Z]{2,5}\s*\d+[A-Za-z]?\s*[—\-–]\s*\d{2,4})',
    ]
    for pat in patterns:
        m = re.search(pat, header)
        if m:
            # 标准化：把各种破折号统一为 -
            num = m.group(1).replace('—', '-').replace('–', '-')
            return num.strip()
    return ""


def _extract_standard_name(text: str, header: str, std_number: str) -> str:
    """从文档头部提取标准名称"""
    # 策略1: 标准编号后面紧跟的中文标题
    if std_number:
        # 直接在header中找编号的位置
        idx = header.find(std_number)
        if idx >= 0:
            # 编号之后的内容
            after = header[idx + len(std_number):].strip()
            # 提取中文标题: 编号后的中文文字，遇到大写英文或行尾停止
            m = re.match(r'([一-鿿（(][一-鿿（）()《》、，。；;：:！!？?/+\-—– 　]{3,80}?)(?:\s*[A-Z][a-z]|\s*\n|\s*$)', after)
            if m:
                name = m.group(1).strip()
                # 去掉尾部英文
                name = re.sub(r'\s+[A-Za-z].*$', '', name).strip()
                if len(name) >= 4:
                    return name

    # 策略2: header中找独立中文长标题行
    for line in header.split('\n')[:30]:
        line = line.strip()
        # 纯中文开头，5-100字，排除前言/引用等
        skip_words = ['前言', '目录', '范围', '引用', '术语', '附录', '本标', '本规',
                      '根据', '依据', '参照', '参见', '中国', '海军标', '国家军']
        if (re.match(r'^[一-鿿（(]', line)
                and 5 <= len(line) <= 100
                and not any(line.startswith(w) for w in skip_words)
                and '依据' not in line[:10] and '根据' not in line[:10]):
            return line

    # 策略3: 标签提取
    m = re.search(r'(?:标准名称|名称)[：:]\s*(.+?)(?:\n|$)', text[:1000])
    if m:
        return m.group(1).strip()

    return ""


def _extract_dates(text: str):
    """从文档头部提取发布和实施日期"""
    publish_date = None
    implement_date = None

    # 优先匹配标准封面格式: 2025-03-01 发布  2025-06-01 实施
    m = re.search(r'(\d{4}[—\-–]\d{1,2}[—\-–]\d{1,2})\s*[发布颁].*?(\d{4}[—\-–]\d{1,2}[—\-–]\d{1,2})\s*[实施执行]', text)
    if m:
        publish_date = parse_date(m.group(1))
        implement_date = parse_date(m.group(2))
        return publish_date, implement_date

    # 单独匹配
    date_map = [
        (r'(?:发布时间|发布日期|颁布日期)[：:\s]*(\d{4}[年—\-–/]\d{1,2}[月—\-–/]\d{1,2}[日]?)', 'publish'),
        (r'(?:实施时间|实施日期|施行日期|执行日期)[：:\s]*(\d{4}[年—\-–/]\d{1,2}[月—\-–/]\d{1,2}[日]?)', 'implement'),
    ]

    dates_found = []
    for pat, _ in date_map:
        m = re.search(pat, text)
        if m:
            parsed = parse_date(m.group(1))
            if parsed:
                dates_found.append(parsed)

    if len(dates_found) >= 1:
        publish_date = dates_found[0]
    if len(dates_found) >= 2:
        implement_date = dates_found[1]

    # 如果还没找到，尝试通用日期格式（优先取开头部分）
    if not publish_date:
        for m in re.finditer(r'(\d{4}-\d{2}-\d{2})', text[:1000]):
            d = parse_date(m.group(1))
            if d and not publish_date:
                publish_date = d
            elif d and not implement_date:
                implement_date = d
                break

    return publish_date, implement_date


def _extract_responsible_unit(text: str) -> str:
    """从文本中提取归口/批准单位"""
    # 封面常见: 中国人民解放军海军装备部　批准
    patterns = [
        r'(中国人民解放军\S+?部)\s*(?:批准|发布)',
        r'(?:归口单位|发布单位|批准单位|主编单位|起草单位|提出单位)[：:]\s*(.+?)(?:\n|$)',
        r'(海军\S{2,8}(?:部|局|处|院|所|中心))',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return ""


def validate_metadata(metadata: dict) -> tuple:
    """校验元数据完整性，返回 (is_valid, missing_fields)"""
    missing = []

    if not metadata.get("standard_name", "").strip():
        missing.append("standard_name")

    if not metadata.get("standard_number", "").strip():
        missing.append("standard_number")

    if metadata.get("doc_status") not in VALID_STATUSES:
        missing.append("doc_status")

    is_valid = len(missing) == 0
    return is_valid, missing


def parse_date(date_str: str) -> Optional[date]:
    """解析多种格式的日期字符串"""
    if not date_str:
        return None

    # 标准化
    date_str = date_str.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-").strip()

    formats = ["%Y-%m-%d", "%Y-%m", "%Y-%m-%d", "%Y%m%d"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    # 尝试只解析年份
    try:
        year = int(re.search(r'(\d{4})', date_str).group(1))
        return date(year, 1, 1)
    except (ValueError, AttributeError):
        return None


def format_metadata_for_display(metadata: dict) -> dict:
    """格式化元数据用于前端展示"""
    display = {}
    field_labels = {
        "standard_number": "标准编号",
        "standard_name": "标准名称",
        "applicable_field": "适用领域",
        "publish_date": "发布时间",
        "implement_date": "实施时间",
        "doc_status": "文档状态",
        "responsible_unit": "归口单位",
    }

    for field, label in field_labels.items():
        value = metadata.get(field, "")
        if isinstance(value, date):
            value = value.strftime("%Y-%m-%d")
        display[label] = value if value else "（未填写）"

    return display
