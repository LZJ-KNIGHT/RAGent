# Description: 知识库管理API，使用硅基流动Embedding模型和本地FAISS向量存储库进行知识库的创建、删除、文件上传、文件删除、搜索等操作。
# ============================================================
# kb_routes.py —— 知识库管理服务（RAG 的地基）
# 职责：知识库的建/删/列（create_kb/delete_kb/list_kbs）、
#       文件上传入库（切块+向量化）、文件删除、混合检索（search_kb）
# 两套存储：① FAISS 向量文件（knowledgebases/库名.faiss/ 目录）
#          ② SQLite 元数据（db_server/info.db 登记库名和描述）
#          两者靠库名弱关联、无跨存储事务 —— 一致性靠代码里的处理顺序与失败补偿保证
# ============================================================
import os
import shutil
import tempfile
from typing import List

import faiss
import jieba
from langchain_openai import OpenAIEmbeddings
from langchain.embeddings.base import Embeddings
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever

from .loader.loader import data_loader
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from fastapi import HTTPException, APIRouter, Body, UploadFile, File, Form
from db_server.base import session
from db_server.knowledge_base_repository import add_kb_to_db, del_kb_from_db
from configs.setting import KB_DIR, FILE_STORAGE_DIR, embedding_model_path, embedding_api_key

kb_router = APIRouter(prefix="/knowledgebase", tags=["knowledge Bases Management"])

# 确保知识库目录存在
if not os.path.exists(KB_DIR):
    os.makedirs(KB_DIR)

# ---------------------------------------------------------------------------
# faiss 在 Windows 上把路径当 ANSI 窄字符交给 C++ 的 fopen，路径里只要有中文
# （知识库名，甚至项目所在目录）就会报 "could not open ...: No such file or directory"，
# 建库直接 500。Python 自己的文件 API 没这个问题，所以把 faiss 的读写包一层：
# 路径含非 ASCII 字符时先落到系统临时目录，再用 shutil 搬到目标位置。
# 只影响 index.faiss；index.pkl 是 Python pickle 写的，本来就正常。
# ---------------------------------------------------------------------------
_faiss_write_index, _faiss_read_index = faiss.write_index, faiss.read_index   # 先保存原始函数


def _ascii_temp_file():
    # 建一个纯 ASCII 路径的临时空文件（系统临时目录通常是 C:\Users\...，全英文）
    fd, path = tempfile.mkstemp(suffix=".faiss")
    os.close(fd)
    return path


def _write_index_unicode_safe(index, path):
    # 猴子补丁的"写"半边：路径纯英文 → 直接走原始函数（快路径）；
    # 含中文 → 先写临时文件，再由 shutil 搬到中文目标路径
    path = os.fspath(path)
    if path.isascii():
        return _faiss_write_index(index, path)
    tmp = _ascii_temp_file()
    try:
        _faiss_write_index(index, tmp)
        # 用 shutil.move 而不是 os.replace：临时目录在 C 盘，知识库可能在别的盘，不能跨盘 rename
        shutil.move(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _read_index_unicode_safe(path):
    # 猴子补丁的"读"半边：含中文路径 → 先把文件拷到 ASCII 临时路径再读
    path = os.fspath(path)
    if path.isascii():
        return _faiss_read_index(path)
    tmp = _ascii_temp_file()
    try:
        shutil.copyfile(path, tmp)
        return _faiss_read_index(tmp)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


faiss.write_index = _write_index_unicode_safe
faiss.read_index = _read_index_unicode_safe

# 创建一个嵌入对象（你可以根据需要调整）
class CustomEmbeddingModel(Embeddings):
    """把硅基流动的 BGE embedding API 包装成 LangChain 认识的格式。
    LangChain 规定向量库需要两个方法：embed_documents（批量，建库/入库用）
    和 embed_query（单条，检索时把用户问题变成向量用）。"""
    def __init__(self, model, model_name):
        self.model = model
        self.model_name = model_name

    def embed_documents(self, texts):
        # 注意：这里逐条发 HTTP 请求 —— 性能优化点（可改成分批批量请求）
        return [self.model.client.create(model=self.model_name, input=text).data[0].embedding for text in texts]

    def embed_query(self, text):
        # 检索侧：把用户问题转成向量，与库内 chunk 向量算相似度
        return self.model.client.create(model=self.model_name, input=text).data[0].embedding
# api_key 统一来自 configs/setting.py（其值读自 config.json）——
# 密钥全项目只在配置文件里出现一处，代码里不落明文
embedding = OpenAIEmbeddings(
            api_key=embedding_api_key,
            base_url="https://api.siliconflow.cn/v1",
            )
embedding_model = CustomEmbeddingModel(embedding, "BAAI/bge-large-zh-v1.5")
# embedding_model = HuggingFaceEmbeddings(model_name=embedding_model_path)


# 知识库名会被直接拿去拼目录名，这几个字符在 Windows 上非法；
# 其中 / 和 \ 还会改变路径层级（填 a/b 会建到 knowledgebases/a/b.faiss 去）。
KB_NAME_ILLEGAL_CHARS = set('\\/:*?"<>|')


def normalize_kb_name(kb_name: str) -> str:
    """校验并规范化知识库名，不合法就抛 400。
    为什么这么严？库名会被直接拼进文件路径建目录 —— 不校验就是路径注入入口：
    名字里带 / 能建到别的层级，带 \\ 和 Windows 非法字符直接报错。"""
    # 空名字会建出 knowledgebases/.faiss 这种垃圾目录，且下拉框里会出现空选项
    kb_name = kb_name.strip()
    if not kb_name:
        raise HTTPException(status_code=400, detail="知识库名称不能为空")

    bad = sorted(set(kb_name) & KB_NAME_ILLEGAL_CHARS)
    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"知识库名称不能包含这些字符：{' '.join(bad)}",
        )
    if not kb_name.isprintable():
        raise HTTPException(status_code=400, detail="知识库名称不能包含不可见字符")
    return kb_name


# 创建知识库的API
@kb_router.post("/create_kb")
async def create_kb(
        kb_name: str = Body(..., description="知识库名称"),
        kb_info: str = Body("", description="知识库内容简介，用于Agent选择知识库。"),

):
    kb_name = normalize_kb_name(kb_name)

    kb_path = os.path.join(KB_DIR, f"{kb_name}.faiss")

    # 检查知识库是否已经存在
    if os.path.exists(kb_path):
        raise HTTPException(status_code=400, detail="知识库已经存在")

    doc = Document(page_content="init", metadata={})
    # "填假人"技巧：FAISS 不允许直接建空索引，必须至少喂一个文档才能初始化骨架。
    # 注意这一步会真的调用一次 embedding API（"init" 也被向量化）
    vector_store = FAISS.from_documents([doc], embedding_model, normalize_L2=True)

    # 查出假文档的 id 再删掉 —— 骨架留下，尸体清走，得到一个合法的空索引
    ids = list(vector_store.docstore._dict.keys())
    vector_store.delete(ids)

    # 保存空的知识库。写入失败时要把半成品目录清掉 ——
    # 否则目录留着、库里又没登记，下次同名建库会一直报"知识库已经存在"，那个名字就废了。
    try:
        vector_store.save_local(kb_path)
    except Exception as e:
        shutil.rmtree(kb_path, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"知识库创建失败：{e}")

    add_kb_to_db(session, kb_name, kb_info)
    # 存储顺序：先 FAISS 文件后 SQLite 登记 —— 后者失败会留下"孤儿库"
    # （目录在、登记本没有），但 list_kbs 读文件系统所以库还能被列出使用

    return {"message": f"知识库 '{kb_name}' 创建成功！"}


# 删除知识库的API：一次删三处 —— 向量目录、原始文件目录、SQLite 登记行；
# 无事务保证，删到一半崩会留孤儿数据（demo 场景靠手动清理）
@kb_router.delete("/delete_kb")
async def delete_kb(kb_name: str):
    kb_path = os.path.join(KB_DIR, f"{kb_name}.faiss")
    kb_files_path = os.path.join(FILE_STORAGE_DIR, kb_name)
    # 检查知识库是否存在
    if not os.path.exists(kb_path):
        raise HTTPException(status_code=404, detail="Database not found")

    # 删除知识库
    shutil.rmtree(kb_path)
    # 删除知识库关联文件
    if os.path.exists(kb_files_path):
        shutil.rmtree(kb_files_path)

    del_kb_from_db(session, kb_name)

    return {"message": f"Database '{kb_name}' deleted successfully"}


# 列出所有知识库的API：真相源是文件系统（扫 .faiss 目录），
# 而不是 SQLite —— 所以即使登记缺失，库依然能被列出
@kb_router.get("/list_kbs")
async def list_kbs():
    kb_files = [f for f in os.listdir(KB_DIR) if f.endswith(".faiss")]
    return {"knowledgebases": kb_files}


# 上传文档入库：整条"写路径"的核心 —— 存原始文件 → 解析 → 切块 → 向量化 → 入库
@kb_router.post("/upload_docs")
async def upload_docs(
        files: List[UploadFile] = File(...),
        kb_name: str = Form(..., description="知识库名称"),
        chunk_size: int = Form(128, description="知识库中单段文本最大长度"),
        chunk_overlap: int = Form(20, description="知识库中相邻文本重合长度"),
):
    kb_path = os.path.join(KB_DIR, f"{kb_name}.faiss")
    kb_file_storage_path = os.path.join(FILE_STORAGE_DIR, kb_name)

    if not os.path.exists(kb_path):
        raise HTTPException(status_code=404, detail="Database not found")

    # 检查知识库对应的文件存储文件夹是否存在，不存在则创建
    os.makedirs(kb_file_storage_path, exist_ok=True)
    updated_file = []
    for file in files:
        # ===== 第一段：把原始文件存到 data/库名/ 目录（留底，删文件时要用） =====
        # 将文件保存到对应知识库的文件夹中
        file_path = os.path.join(kb_file_storage_path, file.filename)
        file_content = file.file.read()

        with open(file_path, "wb") as f:
            f.write(file_content)

        # ===== 第二段：解析 + 切块 =====
        # 解析文本文件内容并分割成小块
        loader = data_loader().get_loader(file_path)
        # 将文档加载为一个文档对象列表
        docs = loader.load()
        # RecursiveCharacterTextSplitter：按分隔符优先级递归切（段落→行→空格→标点），
        # 尽量保住语义完整；chunk_overlap 让相邻块重叠 20 字符防句子被切断
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=[
            "\n\n",
            "\n",
            " ",
            ".",
            ",",
            "，",
            "。",
            ""
        ], )
        # 将文档分割为多个块
        chunks = text_splitter.split_documents(docs)

        # ===== 第三段：向量化 + 入库 =====
        # 注意：load 和 save 都在循环里 —— 每传一个文件就全量读写一遍整个索引，
        # 传 N 个文件 = N 倍全量 IO。优化点：把 load/save 挪到循环外各执行一次
        # 加载知识库
        vectorstore = FAISS.load_local(kb_path, embedding_model, allow_dangerous_deserialization=True)

        # 将文件内容向量化并添加到知识库（add_documents 内部会调 embed_documents）
        vectorstore.add_documents(chunks)

        # 保存更新后的知识库（FAISS 是整体覆盖写、快照式持久化，无增量追加能力）
        vectorstore.save_local(kb_path)

        updated_file.append(file.filename)

    return {"message": f"File '{updated_file}' added to database '{kb_name}' successfully"}


# 删除库内指定文件：原始文件和向量索引里的对应 chunk 要一起删（两处同步）
@kb_router.post("/delete_docs")
async def delete_docs(
        file_names: List[str] = Body(..., examples=[["test.txt"]]),
        kb_name: str = Body(..., description="知识库名称"),
):
    kb_path = os.path.join(KB_DIR, f"{kb_name}.faiss")
    kb_file_storage_path = os.path.join(FILE_STORAGE_DIR, kb_name)

    # 检查知识库是否存在
    if not os.path.exists(kb_path):
        raise HTTPException(status_code=404, detail=f"知识库 {kb_name} 不存在")

    # 加载知识库
    vector_store = FAISS.load_local(kb_path, embedding_model,
                                    allow_dangerous_deserialization=True)

    failed_files = {}
    success_files = []
    for file_name in file_names:
        file_path = os.path.join(kb_file_storage_path, file_name)
        # 检查文件是否存在
        if not os.path.exists(file_path):
            failed_files[file_name] = f"未找到文件 {file_name}"
            continue

        # 尝试删除文件：先删磁盘上的原始文件，再按 metadata 里的 source 路径
        # 反查向量库里属于这个文件的所有 chunk id，逐个从索引中移除
        try:
            os.remove(file_path)
            ids = [
                k
                for k, v in vector_store.docstore._dict.items()
                if v.metadata.get("source").lower() == file_path.lower()
            ]
            if len(ids) > 0:
                vector_store.delete(ids)
                success_files.append(file_name)
            else:
                failed_files[file_name] = f"文件 {file_name} 在向量存储中找不到"
        except Exception as e:
            failed_files[file_name] = str(e)

    # 保存更新后的向量存储
    try:
        vector_store.save_local(kb_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存向量存储时出错: {str(e)}")

    response = {
        "success": success_files,
        "failed": failed_files
    }

    return response


# 混合检索接口：RAG "读路径"的入口（前端查询和 Agent 工具都走这里）
# BM25（关键词）+ FAISS（语义）两路各取 k=2，加权 0.5/0.5 融合排序
@kb_router.post("/search_kb")
async def search_kb(
        kb_name: str = Body(..., description="知识库名称"),
        query: str = Body(..., description="问题")

):
    kb_path = os.path.join(KB_DIR, f"{kb_name}.faiss")

    if not os.path.exists(kb_path):
        raise HTTPException(status_code=404, detail="Database not found")

    # 加载知识库
    vector_store = FAISS.load_local(kb_path, embedding_model,
                                    allow_dangerous_deserialization=True)

    # 防御纵深第一道（库不存在→404，上面）、第二道（库存在但为空→合法空结果）：
    docs = list(vector_store.docstore._dict.values())
    # 空知识库（刚建好还没传文件）直接返回空结果。
    # 否则 BM25Retriever.from_documents([]) 内部 zip(*[]) 解包失败抛 ValueError，
    # 接口 500，Agent 那边只能拿到一句"无法获取信息"。
    if not docs:
        return {"results": []}

    # ===== 路线一：FAISS 向量检索（语义相似）=====
    # 用户问题和 chunk 各自的 embedding 算距离，意思相近就算匹配，
    # 同义词/换种说法也能命中；k=2 表示取最相似的前 2 块
    faiss_retriever = vector_store.as_retriever(search_kwargs={"k": 2})

    # ===== 路线二：BM25 关键词检索 =====
    # 基于词频的经典算法：专名、术语等"字面命中"强；
    # preprocess_func 用 jieba 分词 —— 中文没有空格分词，必须先切词 BM25 才能统计词频
    bm25_retriever = BM25Retriever.from_documents(
        docs,
        preprocess_func=jieba.lcut_for_search,
    )
    bm25_retriever.k = 2  # 设置 BM25 检索器返回的文档数量

    # ===== 融合：两路结果加权合并（各占 50%）=====
    # 互补逻辑：向量检索兜"意思对但字面不同"，BM25 兜"专有名词精确匹配"，
    # 单用任何一路都会漏掉另一路的强项
    ensemble_retriever = EnsembleRetriever(
        retrievers=[bm25_retriever, faiss_retriever], weights=[0.5, 0.5]
    )

    contexts = ensemble_retriever.invoke(query)

    # 只抽出"来源 + 原文"两个字段返回，调用方（前端/工具）不需要其余元数据
    contexts = {
        "results": [{"sources": context.metadata.get("source", ""), "page_contents": context.page_content} for context
                    in contexts],
    }
    return contexts
