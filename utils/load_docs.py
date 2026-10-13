# ============================================================
# load_docs.py —— 万能文件内容读取器（get_file_content）
# 职责：按扩展名选读取方式，把 txt/csv/json/pdf/docx/md/py 统一读成纯文本
# 两个消费方：① loader.py 的 TextContentLoader（知识库入库路径）
#            ② chat_routes 的 files_rag（聊天附件全文直塞路径）
# ============================================================
import json
import os

import fitz
from docx import Document

# 格式不支持时 get_file_content 返回的固定提示串。
# 提成常量是为了让 chat_routes.files_rag 能识别"这不是文件内容，而是读取失败信号"，
# 从而把它替换成写给模型的明确指令（见 files_rag 中的用法）。
UNSUPPORTED_FILE_TIP = "格式不支持，请更换文件！"

# 扫描件 PDF 的 OCR 结果缓存：{缓存键: 识别文本}。
# 缓存键 = (绝对路径, 修改时间, 文件大小) —— 文件被改动后键自然变化，缓存自动失效。
# 为什么要缓存：files_rag 每个请求都会重读一遍附件目录，没缓存的话同一份扫描件
# 会在每条消息里重复 OCR（单页约 2~3 秒），纯浪费。
_OCR_CACHE = {}


def _pdf_ocr_text(file_path):
    """扫描件 PDF 的 OCR 兜底：没有文字层时，把页面渲染成位图交给 Tesseract 识别。

    依赖系统安装 Tesseract（本项目用 conda install -c conda-forge tesseract）。
    语言选 chi_sim+eng —— 中文文档里常混排英文单词、数字。
    dpi=216 是质量与速度的折中：72（默认值）渲染太糊识别差，300 又明显变慢。
    未安装 Tesseract 或识别失败时返回空串，由调用方按"内容为空"处理。
    """
    key = (os.path.abspath(file_path), os.path.getmtime(file_path), os.path.getsize(file_path))
    if key in _OCR_CACHE:
        return _OCR_CACHE[key]

    text = ""
    try:
        with fitz.open(file_path) as pdf_document:
            for page in pdf_document:
                textpage = page.get_textpage_ocr(language="chi_sim+eng", dpi=216, full=True)
                text += page.get_text("text", textpage=textpage) + "\n"
    except Exception:
        # Tesseract 缺失、语言包缺失等异常统一归为"OCR 失败"，不向上抛
        text = ""
    _OCR_CACHE[key] = text
    return text


def get_file_content(file_path):
    filename = os.path.basename(file_path)
    file_extension = os.path.splitext(filename)[1].lower()
    # 读取不同类型的文件内容
    if file_extension == '.txt' or file_extension == '.csv':
        with open(file_path, "r", encoding="utf-8") as f:
            file_content = f.read()
    elif file_extension == '.json':
        with open(file_path, "r", encoding="utf-8") as f:
            file_content = json.dumps(json.load(f), indent=4, ensure_ascii=False)
    elif file_extension == '.pdf':
        file_content = ""
        with fitz.open(file_path) as pdf_document:
            for page_num in range(pdf_document.page_count):
                page = pdf_document[page_num]
                file_content += page.get_text() + "\n"
        # 文字层提取结果为空 → 多半是没有文字层的扫描件/图片型 PDF（整页只有一张图），
        # 换成 OCR 再读一次；OCR 也读不出就保持空串，由 files_rag 的空内容提示兜底
        if not file_content.strip():
            file_content = _pdf_ocr_text(file_path)
    elif file_extension == '.docx':
        file_content = ""
        document = Document(file_path)
        for paragraph in document.paragraphs:
            file_content += paragraph.text + "\n"
    elif file_extension == '.md' or file_extension == '.py':
        with open(file_path, "r", encoding="utf-8") as f:
            file_content = f.read()
    else:
        # 返回固定提示串而非原文：files_rag 识别到它后会替换为给模型的指令
        file_content = UNSUPPORTED_FILE_TIP

    return file_content