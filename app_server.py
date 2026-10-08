# ============================================================
# app_server.py —— 后端总入口（uvicorn 从这里起服务，端口 6605）
# 职责只有三件：创建 FastAPI 应用、把两个路由组挂上来、挂载静态资源目录。
# 本文件不含任何业务逻辑 —— 聊天在 chat/、知识库在 knowledgebase_server/
# ============================================================
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from chat.chat_routes import chat_router
from knowledgebase_server.kb_routes import kb_router
from fastapi.staticfiles import StaticFiles
from configs.setting import MEDIA_DIR

# 创建FastAPI实例
app = FastAPI()

# 允许跨域请求（前后端分离/本地调试时浏览器会拦截跨域，这里全放开）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由：挂上后 6605 端口才"认识" /chat/* 和 /knowledgebase/* 两组地址
app.include_router(chat_router)
app.include_router(kb_router)

# 挂载静态文件目录：整个项目唯一"URL 真的对应磁盘目录"的地方 ——
# code_interpreter 存的图片通过 http://localhost:6605/media/xxx.png 访问
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

# 程序主入口
if __name__ == "__main__":
    # 导入unicorn服务器的包
    import uvicorn

    # 运行服务器：uvicorn 是 ASGI 服务器，异步接口靠它的事件循环驱动
    uvicorn.run(app, host="127.0.0.1", port=6605, log_level="info")
