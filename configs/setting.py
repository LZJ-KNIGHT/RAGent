# ============================================================
# configs/setting.py —— 全局配置中心（模型密钥、路径、超时）
# 所有硬编码的"环境相关"值集中在这里，其他文件只 import 不写死 ——
# 换模型/换端口/挪目录只改本文件
#
# 密钥管理：4 个第三方 key 不落在代码里，统一从同目录的 config.json 读取
# （该文件已被 .gitignore 屏蔽，不会进仓库）。
# 首次运行：复制 config.template.json 为 config.json，填入自己的 key。
# ============================================================
import json
import os

# ---------------- 密钥：从 config.json 读取 ----------------
# 用绝对路径拼配置文件位置，保证从任何工作目录启动（IDE / 命令行）都能找到
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError(
        f"缺少密钥配置文件：{CONFIG_PATH}\n"
        "请把同目录下的 config.template.json 复制为 config.json，并填入自己的 API Key。"
    )

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    _config = json.load(f)


def _required_key(field):
    """取必填密钥：字段缺失或为空（模板默认值）时立刻报错并指明字段名。
    在启动阶段失败，好过带着空 key 跑起来、调用模型时才收到语焉不详的 401"""
    value = _config.get(field)
    if not value:
        raise ValueError(f"config.json 中的 {field} 未填写，请填入真实 key 后重启。")
    return value


# 聊天大模型：硅基流动上的 Qwen 72B（OpenAI 兼容接口）
chat_model_name = "Qwen/Qwen2.5-72B-Instruct"
api_key = _required_key("chat_api_key")
base_url = "https://api.siliconflow.cn/v1"

# 向量化密钥（供 knowledgebase_server/kb_routes.py 调硅基流动 embedding 接口）
embedding_api_key = _required_key("embedding_api_key")

# serpapi 网络搜索密钥（供 tools/web_search.py 使用）
serpapi_key = _required_key("serpapi_key")

# 心知天气密钥（供 tools/weather_check.py 使用）
seniverse_key = _required_key("seniverse_key")

# ---------------- 以下为非敏感配置，直接写在代码里 ----------------
embedding_model_path = "./models/AI-ModelScope/bge-large-zh-v1___5"

# 存储数据库的路径（FAISS 向量索引目录；每个库一个 <库名>.faiss 子目录）
KB_DIR = "./knowledgebases"
TEMP_KB_DIR = "./temp/knowledgebases"

# 存储文件的路径（上传文档的原始文件留底；temp 版给聊天附件用）
FILE_STORAGE_DIR = "./data"
TEMP_FILE_STORAGE_DIR = "./temp/data"

# 知识库信息数据库的路径
SQLALCHEMY_DATABASE = "./db_server/data/"
# 知识库信息数据库的URI
SQLALCHEMY_DATABASE_URI = "sqlite:///./db_server/data/info.db"

# 设置超时：请求大模型/工具/检索的统一上限（秒）
TIME_OUT = 60

# 媒体文件保存路径（code_interpreter 画出的图存这里，挂载为 /media 路由）
MEDIA_DIR = "./temp/medias"