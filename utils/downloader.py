# ============================================================
# downloader.py —— 模型下载脚本（一次性工具，平时不运行）
# 作用：从 ModelScope 拉取 bge embedding 模型存到 models/ 目录，
# 供 kb_routes_local.py 的 HuggingFaceEmbeddings 本地模式使用（备选方案）
# ============================================================
from modelscope.hub.snapshot_download import snapshot_download
# llm_model_dir = snapshot_download('Qwen/Qwen2.5-0.5B-Instruct',cache_dir='models')
emb_model_dir = snapshot_download('AI-ModelScope/bge-large-zh-v1.5',cache_dir='models')