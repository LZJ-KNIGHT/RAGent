# ============================================================
# loader/loader.py —— 文件加载器工厂（解析层的"格式翻译官"）
# 职责：按扩展名挑一个 LangChain loader，把任意格式文件统一读成
#       Document 对象列表（page_content=正文，metadata.source=来源路径）
# 上传链路位置：kb_routes.upload_docs 里 data_loader().get_loader(path) 这一步
# ============================================================
import os
from fastapi import HTTPException
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders import TextLoader, CSVLoader
from langchain_core.documents import Document
from utils.load_docs import get_file_content


class TextContentLoader:
    """把 utils.load_docs 支持的文件读成单个 Document，供知识库上传使用。"""

    def __init__(self, file_path):
        self.file_path = file_path

    def load(self):
        return [Document(page_content=get_file_content(self.file_path),
                         metadata={"source": self.file_path})]


class data_loader:
    def get_loader(self, file_path):
        # 根据文件格式选择适当的loader
        _, file_extension = os.path.splitext(file_path)
        if file_extension == ".txt":
            loader = TextLoader(file_path, encoding='utf-8')
        elif file_extension == ".pdf":
            loader = PyPDFLoader(file_path)
        elif file_extension == ".md":
            # markdown 本质是纯文本，用 TextLoader 即可，避免引入 unstructured 依赖
            loader = TextLoader(file_path, encoding='utf-8')
        elif file_extension == ".csv":
            loader = CSVLoader(file_path)
        elif file_extension in (".docx", ".json", ".py"):
            # 复用 utils/load_docs 的读取逻辑，无需额外依赖
            loader = TextContentLoader(file_path)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format")

        return loader
