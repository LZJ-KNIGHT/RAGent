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
    elif file_extension == '.docx':
        file_content = ""
        document = Document(file_path)
        for paragraph in document.paragraphs:
            file_content += paragraph.text + "\n"
    elif file_extension == '.md' or file_extension == '.py':
        with open(file_path, "r", encoding="utf-8") as f:
            file_content = f.read()
    else:
        file_content = "格式不支持，请更换文件！"

    return file_content