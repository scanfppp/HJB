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


def _normalize_fullwidth(text: str) -> str:
    """全角字符归一化：全角字母数字符号 → 半角"""
    result = []
    for ch in text:
        code = ord(ch)
        # 全角字母 A-Z (FF21-FF3A) → 半角 (41-5A)
        if 0xFF21 <= code <= 0xFF3A:
            result.append(chr(code - 0xFF21 + 0x41))
        # 全角字母 a-z (FF41-FF5A) → 半角 (61-7A)
        elif 0xFF41 <= code <= 0xFF5A:
            result.append(chr(code - 0xFF41 + 0x61))
        # 全角数字 ０-９ (FF10-FF19) → 半角 (30-39)
        elif 0xFF10 <= code <= 0xFF19:
            result.append(chr(code - 0xFF10 + 0x30))
        # 全角符号 ．／－（FF0E, FF0F, FF0D）→ 半角 . / -
        elif code == 0xFF0E:
            result.append('.')
        elif code == 0xFF0F:
            result.append('/')
        elif code == 0xFF0D:
            result.append('-')
        elif code == 0xFF08:
            result.append('(')
        elif code == 0xFF09:
            result.append(')')
        elif code == 0xFF1A:
            result.append(':')
        elif code == 0xFF0C:
            result.append(',')
        else:
            result.append(ch)
    return ''.join(result)


def extract_metadata_from_text(text: str, file_name: str = "", extracted_title: str = "") -> dict:
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

    # 全角归一化（处理 PDF CID 字体乱码）
    text = _normalize_fullwidth(text)
    if extracted_title:
        extracted_title = _normalize_fullwidth(extracted_title)

    # 取文档头部（前800字），标准编号和名称通常在这里
    header = text[:800]
    # 清理：去掉"中国人民解放军海军标准"等前缀干扰
    header_clean = re.sub(r'中国人民解放军海军标准\s*', '', header)

    # 1. 从文档头部提取标准编号
    #    格式: HJB 590B-2025, GJB 4072B-2023 等
    #    优先匹配紧跟标题文字的编号（行首或紧接中文前）
    number = _extract_standard_number_from_header(header_clean)
    if not number:
        number = _extract_standard_number_from_header(text[:3000])
    metadata["standard_number"] = number

    # 2. 标准名称：优先使用外部传入的标题，否则正则提取（均需过乱码检测）
    if extracted_title and not _looks_garbled(extracted_title):
        metadata["standard_name"] = extracted_title
    else:
        name = _extract_standard_name(text, header_clean, metadata["standard_number"])
        metadata["standard_name"] = name if name and not _looks_garbled(name) else ""

    # 3. 从文件名补充
    if not metadata["standard_name"] and file_name:
        base = file_name.rsplit(".", 1)[0]
        # 去掉可能的时间戳前缀
        base = re.sub(r'^\d+_', '', base)
        if len(base) >= 5:
            metadata["standard_name"] = base
    if not metadata["standard_number"] and file_name:
        metadata["standard_number"] = _extract_standard_number_from_filename(file_name)

    # 如果内容提取的编号是"引用标准"（GB/T 1.1 等），或文件名能提供更精确的编号，优先用文件名
    if metadata["standard_number"] and file_name:
        content_num = metadata["standard_number"].replace(' ', '')
        # 情况1：引用标准
        if content_num in _META_STANDARDS or any(
            content_num.startswith(ms) for ms in _META_STANDARDS
        ):
            fn_num = _extract_standard_number_from_filename(file_name)
            if fn_num and fn_num.replace(' ', '') != content_num:
                metadata["standard_number"] = fn_num
                logger.info(f"编号从引用标准替换为文件名: {content_num} → {fn_num}")
        # 情况2：内容编号与文件名编号不同（pdfplumber 丢失小数点等）
        else:
            fn_num = _extract_standard_number_from_filename(file_name)
            if fn_num:
                fn_compact = fn_num.replace(' ', '')
                if fn_compact != content_num and len(fn_compact) > len(content_num):
                    metadata["standard_number"] = fn_num
                    logger.info(f"编号从文件名补充精度: {content_num} → {fn_num}")

    # 归一化编号格式
    if metadata["standard_number"]:
        num = metadata["standard_number"]
        # OCR 常见噪声：空格+连字符+空格 → 连字符
        num = re.sub(r'\s*[—\-–一]\s*', '-', num)
        # 字母前缀和数字之间加空格（GB/T33479 → GB/T 33479）
        num = re.sub(r'^([A-Z]{2,6}(?:/[A-Z])?)\s*(\d)', r'\1 \2', num)
        metadata["standard_number"] = num
        # 修正 PDF 解析导致的点号丢失：GB/T 1 1 → GB/T 1.1
        metadata["standard_number"] = re.sub(
            r'(\d)\s{1,3}(\d)',
            r'\1.\2',
            metadata["standard_number"]
        )
        # 清理多余空格
        metadata["standard_number"] = re.sub(r'\s{2,}', ' ', metadata["standard_number"])

    # 4. 提取日期（从头部优先）
    metadata["publish_date"], metadata["implement_date"] = _extract_dates(text[:3000])

    # 5. 提取归口单位
    metadata["responsible_unit"] = _extract_responsible_unit(text[:2000])

    return metadata


# 所有标准文档的"规范性引用文件"章节都会引用的元标准
_META_STANDARDS = {
    'GB/T 1.1', 'GB/T1.1', 'GB/T 1.2', 'GB/T1.2',
    'GB/T 1', 'GB/T1',
}


def _extract_standard_number_from_filename(file_name: str) -> str:
    """从文件名中提取标准编号，支持多种命名格式"""
    base = file_name.rsplit(".", 1)[0]
    # 清理常见干扰字符
    base = re.sub(r'[_+=\s]+', ' ', base)

    # === 策略1：标准格式 字母开头+数字+年份（如 GB 39800.8-2024、HJB 590B-2025）===
    m = re.search(r'([A-Z]{2,6}\s*(?:/[A-Z])?\s*\d+(?:\.\d+)?[A-Za-z]?\s*[-–—]?\s*\d{2,4})', base)
    if m:
        result = m.group(1).replace('—', '-').replace('–', '-').replace('一', '-')
        return _normalize_standard_number(result)

    # === 策略2：数字开头-年份-类型（如 33479-2016-gbt-cd-300）===
    # 匹配: 数字(4+) - 年份(4) - 类型字母(含/和数字) - 后缀
    # 类型缩写映射
    _TYPE_MAP = {
        'gbt': 'GB/T', 'gb': 'GB', 'gjb': 'GJB', 'hjb': 'HJB',
        'cb': 'CB', 'wj': 'WJ', 'qj': 'QJ', 'hb': 'HB', 'sj': 'SJ',
        'cbt': 'CB/T', 'hbt': 'HB/T', 'sjt': 'SJ/T',
        'qgbt': 'GB/T', 'qgb': 'GB',
    }
    m = re.search(r'(\d{4,})\s*[-–—]\s*(\d{4})\s*[-–—]\s*([a-z]{2,6}(?:[/.][a-z])?)(?:[-–—\s]|$)', base, re.IGNORECASE)
    if m:
        num = m.group(1)
        year = m.group(2)
        typ = m.group(3).lower().replace('.', '/')
        prefix = _TYPE_MAP.get(typ, typ.upper())
        return f"{prefix} {num}-{year}"

    return ""


def _normalize_standard_number(num: str) -> str:
    """修正文件名中常见的简写：GBT → GB/T，GBZ → GB/Z 等"""
    # 匹配: 1-2个大写字母 + T/Z + 空格/数字（如 GBT 47118 → GB/T 47118）
    m = re.match(r'^([A-Z]{1,2})([TZ])\s+(\d)', num)
    if m:
        return f"{m.group(1)}/{m.group(2)} {num[m.start(3):]}"
    return num


def _extract_standard_number_from_header(header: str) -> str:
    """从文档头部提取标准编号 — 收集所有候选，按位置+上下文评分选最优"""
    patterns = [
        # HJB 590B-2025 或 HJB 590B—2025（带年份）
        r'(HJB\s*\d+(?:\.\d+)?[A-Za-z]?\s*[—\-–一]\s*\d{4})',
        # GJB 4072B-2023, GJB 150.1A-2009（带点号+字母+年份）
        r'(GJB[/A-Za-z]*\s*\d+(?:\.\d+)?[A-Za-z]?\s*[—\-–一]\s*\d{4})',
        # GB/T 1.1-2020, CB/T 4000-2005 等
        r'([A-Z]{2,6}(?:/[A-Z](?:\s*[A-Z])?)?\s*\d+(?:\.\d+)?[A-Za-z]?\s*[—\-–一]\s*\d{2,4})',
        # Q/JB xxx-xxxx, Q/HJB xxx-xxxx
        r'([A-Z]/[A-Z]{2,5}\s*\d+(?:\.\d+)?[A-Za-z]?\s*[—\-–一]\s*\d{2,4})',
        # 标签式: "标准编号：GJB 150.1A-2009"
        r'(?:标准编号|标准号|编号|文件编号)[：:\s]*([A-Z]{2,6}(?:/[A-Z])?\s*\d+(?:\.\d+)?[A-Za-z]?\s*[—\-–一]?\s*\d{0,4})',
        # 无年份后缀: HJB 590B, GJB 150A
        r'([HG]JB[/A-Za-z]*\s*\d+(?:\.\d+)?[A-Za-z]?)',
        # 其他军标: WJ, QJ, HB, SJ, CB 等
        r'([WQHS]J\s*\d+(?:\.\d+)?[A-Za-z]?\s*[—\-–一]?\s*\d{0,4})',
    ]

    # 收集所有候选: (位置, 编号, 模式优先级)
    candidates = []
    seen = set()
    for pi, pat in enumerate(patterns):
        for m in re.finditer(pat, header):
            num = m.group(1).strip()
            num = num.replace('—', '-').replace('–', '-').replace('一', '-')
            num = num.rstrip('-').strip()
            key = num.replace(' ', '')
            if re.search(r'\d', num) and len(num) >= 3 and key not in seen:
                seen.add(key)
                candidates.append((m.start(), num, pi))

    if not candidates:
        return ""

    # 只有一个候选，直接返回
    if len(candidates) == 1:
        return candidates[0][1]

    # 评分：分数越低越好
    def _score(pos, num, pi):
        s = 0
        # 位置分：越靠前越好（文档自身编号通常在封面）
        s += pos
        # 元标准罚分：GB/T 1.1 等（但有其他候选时才罚）
        if num.replace(' ', '') in _META_STANDARDS:
            s += 500
        # 密度罚分：200字内其他标准号越多 → 越像引用章节
        nearby = sum(1 for p, n, _ in candidates
                     if abs(p - pos) < 200 and n != num)
        s += nearby * 80
        # 模式优先级：HJB/GJB 模式（pi=0,1）优先于通用模式
        s += pi * 30
        return s

    candidates.sort(key=lambda c: _score(*c))
    best = candidates[0][1]
    logger.info(f"标准编号候选{len(candidates)}个，选定: {best}")
    return best


def _looks_garbled(text: str) -> bool:
    """检测文本是否疑似 PDF CID 字体乱码（含过多生僻字符）"""
    if not text:
        return False
    rare = 0
    for ch in text:
        code = ord(ch)
        # 排除 CJK 基本区 (U+4E00–U+9FFF) — 常用汉字
        if 0x4E00 <= code <= 0x9FFF:
            continue
        # 排除 CJK 扩展 A 区 (U+3400–U+4DBF) — 仍属正常汉字
        if 0x3400 <= code <= 0x4DBF:
            continue
        # 排除基本 ASCII 和常见符号
        if code <= 0x007E:
            continue
        # 排除全角标点 (U+FF00–U+FFEF)
        if 0xFF00 <= code <= 0xFFEF:
            continue
        # 排除 CJK 兼容区 (U+F900–U+FAFF)
        if 0xF900 <= code <= 0xFAFF:
            continue
        # 排除常用 Unicode 符号区 (U+2000–U+27FF)
        if 0x2000 <= code <= 0x27FF:
            continue
        # 剩余字符视为可疑（PUA、增补汉字、emoji 等）
        rare += 1
    # 超过 30% 的可疑字符视为乱码（放宽阈值，避免误杀常用字）
    return rare > max(2, len(text) * 0.3)


# 标准文档封面常见的机构抬头（含空格展开的变体），不应被当作标准名
_BOILERPLATE_PATTERNS = [
    '中华人民共和国国家标准', '中华人民共和国国家军用标准',
    '中国人民解放军海军标准', '国家市场监督管理总局',
    '中国国家标准化管理委员会', '中华人民共和国国家质量监督检验检疫总局',
    '中国标准出版社', '全国标准化技术委员会',
]


def _is_boilerplate(text: str) -> bool:
    """检测文本是否为标准封面机构抬头（含 PDF/OCR 导致的字符错误）"""
    compact = re.sub(r'\s+', '', text)
    for bp in _BOILERPLATE_PATTERNS:
        if compact == bp or compact.startswith(bp):
            return True
        # 模糊匹配：至少 80% 字符相同（容忍 OCR 错字如"国宾"→"国家标准"）
        if len(compact) >= 8 and len(bp) >= 8:
            common = sum(1 for a, b in zip(compact, bp) if a == b)
            if common / max(len(compact), len(bp)) >= 0.7:
                return True
    return False


def _is_cid_garbled(text: str) -> bool:
    """检测文本是否疑似 CID 字体映射乱码"""
    if not text or len(text) < 10:
        return False
    pua = 0
    ascii_symbols = 0
    cjk = 0
    total = len(text)
    for ch in text:
        code = ord(ch)
        if 0xE000 <= code <= 0xF8FF:
            pua += 1
        if 0x21 <= code <= 0x2F or 0x3A <= code <= 0x40 or 0x5B <= code <= 0x60 or 0x7B <= code <= 0x7E:
            ascii_symbols += 1
        if 0x4E00 <= code <= 0x9FFF:
            cjk += 1
    # PUA 字符：一个就算
    if pua > 0:
        return True
    # ASCII 符号密集 + 几乎没有 CJK → CID 符号乱码
    if total > 100 and ascii_symbols > total * 0.35 and cjk < total * 0.15:
        return True
    return False


def _extract_standard_name(text: str, header: str, std_number: str) -> str:
    """从文档头部提取标准名称"""
    # 扩大搜索范围到前 3000 字
    search_text = text[:3000]

    # 策略1: 标准编号后面紧跟的中文标题
    if std_number:
        # 尝试多种编号写法（有/无空格、hyphen/em dash、全角符号）
        variants = [
            std_number,
            std_number.replace(' ', ''),
            std_number.replace('-', '—'),
            std_number.replace('-', '—').replace(' ', ''),
            std_number.replace('-', '一'),
            std_number.replace('-', ' 一 '),
            std_number.replace('-', '一').replace(' ', ''),
            std_number.replace('/', '／'),
        ]
        for variant in variants:
            idx = search_text.find(variant)
            if idx < 0:
                continue
            after = search_text[idx + len(variant):]
            # 跳过编号后的短分隔符
            after = re.sub(r'^[\s\-–—：:】〕〗\n\r,，]{1,10}', '', after)
            # 跳过"代替"行（OCR 可能带空格：代 替）
            after = re.sub(r'^代\s*替[^\n]*\n?', '', after)
            after = re.sub(r'^[，,\n\r]{1,4}', '', after)
            after = after.strip()
            # 提取标题：中文/数字开头，支持多行和英文字母（标准号内），遇到纯英文行或空行停止
            m = re.match(
                r'([一-鿿（(0-9０-９]'
                r'[一-鿿（）()《》、，。；;：:！!？?0-9０-９A-Za-z/+\-—– 　·ＩＣＳＣ\n\r]{3,150}?)'
                r'(?:\s{2,}|\s*\n\s*\n|\s*\n[A-Z][a-z]{2,}|\s*[A-Z]{4,}|\s*$)',
                after
            )
            if m:
                name = m.group(1).strip()
                # 去掉尾部英文行
                name = re.sub(r'\n[A-Za-z].*$', '', name, flags=re.DOTALL)
                name = name.strip()
                # 压缩内部单换行（跨行标题合并），保留双换行
                name = re.sub(r'(?<!\n)\n(?!\n)', '', name)
                # 压缩字符间多余空格（PDF 排版 artifact）
                name = re.sub(r'([第])\s+', r'\1', name)
                # 合并孤立数字到"第x部分"结构中：如 "第部分 船舶8" → "第8部分 船舶"
                name = re.sub(r'第部分\s+(.+?)(\d)', r'第\2部分 \1', name)
                # 清理尾部残留符号和空格
                name = re.sub(r'[：:—–\s\d]+$', '', name)
                name = re.sub(r'[!！]{2,}', '', name)
                name = re.sub(r'\s*!\s*', '', name)
                name = name.strip()
                if len(name) >= 4 and not _looks_garbled(name) and not _is_boilerplate(name) and not _is_cid_garbled(name):
                    return name

    # 策略2: 在前 1500 字内找独立中文标题行
    for line in search_text[:1500].split('\n')[:40]:
        line = line.strip()
        if not re.match(r'^[一-鿿（(]', line):
            continue
        # 去掉字符间空格（PDF 排版展开）
        line_compact = re.sub(r'\s+', '', line)
        if len(line_compact) < 5 or len(line_compact) > 120:
            continue
        if _looks_garbled(line) or _is_boilerplate(line) or _is_cid_garbled(line):
            continue
        # 排除非标题行（无论长度）
        skip_words = ['前言', '目录', '范围', '引用', '术语', '附录', '本标', '本规',
                      '根据', '依据', '参照', '参见', '中国', '海军标', '国家军', '归口',
                      'ICS', 'CCS', '代替', '目次']
        if any(line_compact.startswith(w) for w in skip_words):
            continue
        if '依据' in line_compact[:10] or '根据' in line_compact[:10]:
            continue
        # ≥10 个实际字符的行大概率是标题
        if len(line_compact) >= 10:
            return line_compact
        # 短文直接返回
        return line_compact

    # 策略3: 标签提取
    m = re.search(r'(?:标准名称|名称|文件名称|标准)[：:]\s*(.+?)(?:\n|$)', text[:2000])
    if m:
        name = m.group(1).strip()
        if len(name) >= 4 and not _looks_garbled(name) and not _is_boilerplate(name) and not _is_cid_garbled(name):
            return name

    return ""


def _extract_dates(text: str):
    """从文档头部提取发布和实施日期"""
    publish_date = None
    implement_date = None

    # 优先匹配标准封面格式: 2025-03-01 发布  2025-06-01 实施
    m = re.search(r'(\d{4}[—\-–一]\d{1,2}[—\-–一]\d{1,2})\s*[发布颁].*?(\d{4}[—\-–一]\d{1,2}[—\-–一]\d{1,2})\s*[实施执行]', text)
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
