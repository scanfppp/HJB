"""
文档解析器 — 支持 PDF（含扫描版OCR via Tesseract）、DOCX、TXT
"""

import os
from collections import defaultdict
from config.settings import SUPPORTED_FORMATS, UPLOAD_DIR, SKIP_TITLE_PREFIXES
from utils.logger import get_logger

logger = get_logger(__name__)

_tesseract_ok = None  # None=未检测, True=可用, False=不可用


def _check_tesseract():
    """检测 Tesseract 是否可用（只检测一次）"""
    global _tesseract_ok
    if _tesseract_ok is not None:
        return _tesseract_ok

    import shutil

    # 多平台查找 tesseract
    tesseract_path = shutil.which("tesseract")  # Linux / Docker PATH
    if not tesseract_path:
        win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(win_path):
            tesseract_path = win_path

    if not tesseract_path:
        logger.warning("Tesseract 未安装，扫描版PDF将无法OCR识别")
        _tesseract_ok = False
        return False

    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        # 项目本地中文语言包
        local_tessdata = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tessdata")
        if os.path.exists(os.path.join(local_tessdata, "chi_sim.traineddata")):
            os.environ["TESSDATA_PREFIX"] = local_tessdata
        _tesseract_ok = True
        logger.info(f"Tesseract OCR 就绪 ({tesseract_path})")
        return True
    except ImportError:
        logger.warning("pytesseract 未安装: pip install pytesseract")
        _tesseract_ok = False
        return False
    except Exception as e:
        logger.warning(f"Tesseract 配置失败: {e}")
        _tesseract_ok = False
        return False


def _extract_title_from_pdf(file_path: str) -> str:
    """从 PDF 首页提取大标题 — 最大字号文本"""
    import pdfplumber
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages:
                return ""
            page = pdf.pages[0]
            chars = page.chars
            if not chars:
                return ""
            by_size = defaultdict(list)
            for c in chars:
                size_key = round(float(c.get("height", 0)), 1)
                if size_key > 0:
                    by_size[size_key].append(c)
            if not by_size:
                return ""
            for size in sorted(by_size.keys(), reverse=True):
                chars_at_size = sorted(by_size[size], key=lambda c: (c["top"], c["x0"]))
                lines = []
                current_line = []
                current_top = None
                for c in chars_at_size:
                    if current_top is None or abs(c["top"] - current_top) < 3:
                        current_line.append(c["text"])
                        current_top = c["top"]
                    else:
                        lines.append("".join(current_line).strip())
                        current_line = [c["text"]]
                        current_top = c["top"]
                if current_line:
                    lines.append("".join(current_line).strip())
                for line in lines:
                    if len(line) >= 5 and not any(line.startswith(p) for p in SKIP_TITLE_PREFIXES):
                        return line
    except Exception as e:
        logger.warning(f"标题提取失败: {e}")
    return ""


def parse_file(file_path: str, force_ocr: bool = False) -> str:
    """根据文件类型自动选择解析器"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    ext = os.path.splitext(file_path)[1].lower().lstrip(".")
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的文件格式: .{ext}")
    if ext == "pdf":
        return parse_pdf(file_path, force_ocr=force_ocr)
    elif ext == "docx":
        return parse_docx(file_path)
    elif ext == "txt":
        return parse_txt(file_path)
    else:
        raise ValueError(f"未实现解析器: {ext}")


def parse_pdf(file_path: str, force_ocr: bool = False) -> str:
    """PDF解析：文字型用 pdfplumber，扫描版自动 OCR"""
    import pdfplumber

    if force_ocr:
        return _ocr_pdf(file_path)

    all_text = []
    total_chars = 0
    with pdfplumber.open(file_path) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_text.append(text)
                total_chars += len(text)

    avg_chars = total_chars / max(page_count, 1)
    if avg_chars < 30 and page_count > 1:
        logger.info(f"检测到扫描版PDF (平均{avg_chars:.0f}字/页)，切换OCR")
        return _ocr_pdf(file_path)

    result = "\n".join(all_text)
    # PDF CID字体全角归一化
    result = _fix_pdf_fullwidth(result)

    # CID 乱码检测：PUA 私用区字符 + ASCII 符号密集
    pua_count = sum(1 for ch in result[:2000] if 0xE000 <= ord(ch) <= 0xF8FF)
    sample = result[:2000]
    ascii_symbols = sum(1 for ch in sample if 0x21 <= ord(ch) <= 0x2F or 0x3A <= ord(ch) <= 0x40 or 0x5B <= ord(ch) <= 0x60 or 0x7B <= ord(ch) <= 0x7E)
    cjk_chars = sum(1 for ch in sample if 0x4E00 <= ord(ch) <= 0x9FFF)
    ascii_garbled = len(sample) > 100 and ascii_symbols > len(sample) * 0.35 and cjk_chars < len(sample) * 0.15
    should_ocr = pua_count > 10 or ascii_garbled
    if should_ocr:
        logger.info(f"检测到CID字体乱码(PUA:{pua_count} ASCII:{ascii_garbled})，OCR前2页取元数据")
        first2 = _ocr_pdf_pages(file_path, max_pages=2)
        if first2 and not first2.startswith("此PDF为扫描版"):
            result = first2 + "\n【CID_GARBLED】\n" + result

    logger.info(f"PDF文字提取: {page_count}页, {total_chars}字")
    return result


def _fix_pdf_fullwidth(text: str) -> str:
    """修复 PDF CID 字体导致的全角字母数字"""
    result = []
    for ch in text:
        code = ord(ch)
        if 0xFF21 <= code <= 0xFF3A:   # 全角 A-Z → 半角
            result.append(chr(code - 0xFF21 + 0x41))
        elif 0xFF41 <= code <= 0xFF5A:  # 全角 a-z → 半角
            result.append(chr(code - 0xFF41 + 0x61))
        elif 0xFF10 <= code <= 0xFF19:  # 全角 0-9 → 半角
            result.append(chr(code - 0xFF10 + 0x30))
        elif code == 0xFF0F:            # 全角 ／ → /
            result.append('/')
        elif code == 0xFF0D:            # 全角 － → -
            result.append('-')
        elif code == 0xFF0E:            # 全角 ． → .
            result.append('.')
        else:
            result.append(ch)
    return ''.join(result)


def _ocr_pdf_pages(file_path: str, max_pages: int = 2) -> str:
    """Tesseract OCR 指定页数（用于上传时快速提取元数据）"""
    if not _check_tesseract():
        return ""
    import fitz, pytesseract
    from PIL import Image

    doc = fitz.open(file_path)
    pages = min(doc.page_count, max_pages)
    texts = []
    for i in range(pages):
        pix = doc[i].get_pixmap(dpi=200)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        text = pytesseract.image_to_string(img, lang="chi_sim+eng", config="--oem 1 --psm 3")
        if text:
            texts.append(text)
    doc.close()
    return "\n".join(texts)


def _ocr_pdf(file_path: str) -> str:
    """Tesseract OCR 全页 PDF：200DPI + 并行 + 加速参数"""
    if not _check_tesseract():
        return (
            "此PDF为扫描版（图片型），需要安装Tesseract OCR才能识别。\n"
            "1. 运行: winget install UB-Mannheim.TesseractOCR\n"
            "2. 下载中文语言包到 data/tessdata/chi_sim.traineddata\n"
            "3. pip install pytesseract"
        )

    import fitz
    import pytesseract
    from PIL import Image
    from concurrent.futures import ThreadPoolExecutor, as_completed

    doc = fitz.open(file_path)
    page_count = doc.page_count

    # Tesseract 加速: OEM 1=LSTM only, PSM 3=自动检测
    tesseract_config = '--oem 1 --psm 3'

    def ocr_page(page_num):
        try:
            page = doc.load_page(page_num)
            # 150 DPI，军用标准字体规整，精度足够
            pix = page.get_pixmap(dpi=150)
            img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img, lang='chi_sim+eng', config=tesseract_config)
            return (page_num, text.strip() if text else '')
        except Exception as e:
            logger.warning(f"OCR第{page_num+1}页失败: {e}")
            return (page_num, '')

    # 并行处理（最多4线程）
    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(ocr_page, p): p for p in range(page_count)}
        for future in as_completed(futures):
            page_num, text = future.result()
            results[page_num] = text

    doc.close()

    all_text = [results[p] for p in sorted(results.keys()) if results[p]]
    full_text = "\n".join(all_text)
    logger.info(f"OCR完成: {page_count}页, {len(full_text)}字")
    return full_text if full_text.strip() else "OCR未能识别到文字内容"


def parse_docx(file_path: str) -> str:
    """DOCX解析"""
    from docx import Document
    doc = Document(file_path)
    all_text = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            if para.style.name.startswith("Heading"):
                level = para.style.name.replace("Heading ", "")
                prefix = "#" * int(level) if level.isdigit() else "#"
                all_text.append(f"\n{prefix} {text}\n")
            else:
                all_text.append(text)
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            all_text.append(" | ".join(cells))
    logger.info(f"DOCX解析完成: {file_path}")
    return "\n".join(all_text)


def parse_txt(file_path: str) -> str:
    """TXT解析，自动检测编码"""
    for encoding in ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read()
            logger.info(f"TXT解析完成: {file_path}, 编码={encoding}")
            return content
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"无法识别文件编码: {file_path}")


def save_uploaded_file(uploaded_file) -> str:
    """保存上传文件"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    import time
    original_name = uploaded_file.name
    safe_name = f"{int(time.time())}_{original_name}"
    save_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    logger.info(f"文件已保存: {save_path}")
    return save_path


def get_file_info(file_path: str) -> dict:
    """获取文件基本信息"""
    ext = os.path.splitext(file_path)[1].lower().lstrip(".")
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    return {
        "file_path": file_path,
        "file_type": ext,
        "file_size_mb": round(size_mb, 2),
        "file_name": os.path.basename(file_path),
    }
