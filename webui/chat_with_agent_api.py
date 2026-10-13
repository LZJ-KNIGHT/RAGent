# ============================================================
# chat_with_agent_api.py —— 前端侧的"打包员 + 快递员"
# 职责：把界面上收集的问题/历史/滑条参数打包成 HTTP 请求发给后端，
#       再把后端流式吐回的 token 转交给 Gradio 界面显示
# 关键约定：data 字典的 key 必须和 chat_routes.py 的 Form(...) 声明一一对应，
# 对不上后端会静默用默认值（不报错）—— 排查参数问题先对两边字段名
# ============================================================
# 定义后台 API 的 URL
import json
import requests

chat_with_agent_url = "http://127.0.0.1:6605/chat/agent_chat"
chat_url = "http://127.0.0.1:6605/chat/chat"


def _file_paths(prompt_files):
    """兼容两种 gradio 的传参形状。

    gradio 4.x: ChatInterface 的取词事件带 preprocess=False，原样收到前端 JSON，
                files 是 [{"path": "...", ...}, ...]（字典列表）
    gradio 5.x: 该事件去掉了 preprocess=False，MultimodalTextbox.preprocess 返回
                [f.path for f in payload.files]，files 是 ["...", ...]（字符串列表）
    """
    return [f["path"] if isinstance(f, dict) else f for f in (prompt_files or [])]


def chat_with_agent(prompt, history, sys_prompt, history_len, temperature, max_tokens, stream, session_id):
    # ===== 打包阶段：把界面参数组装成 HTTP 请求 =====
    # 构建文件和表单数据：把附件文件以二进制读出，塞进 multipart 表单的 files 字段
    file_paths = _file_paths(prompt["files"])
    files = [('files', (open(file_path, 'rb'))) for file_path in file_paths]
    # query 只放用户输入的文本。附件内容由后端 files_rag 读好后放进 documents 传给模型 ——
    # 绝不能把本地路径拼进来：模型看到"能直接打开的文件路径"，就会绕开 documents，
    # 自己用 code_interpreter 去读文件（而不是使用后端预读好的内容）
    query = f'{prompt["text"]}\n'
    # 构建请求数据：历史是 dict 列表，HTTP 表单只收字符串，所以 str(h) 逐个序列化
    # （后端用 literal_eval 再还原回来 —— 两边是一对协议）
    data = {
        "query": query,
        "sys_prompt": sys_prompt,
        "history_len": history_len,
        "history": [str(h) for h in history],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "session_id": session_id,
    }

    # ===== 发送 + 转发阶段 =====
    # stream=True：逐块读取响应而不等全部完成 —— 这是前端打字机效果的起点
    try:
        response = requests.post(chat_with_agent_url, files=files, data=data, stream=True)
        if response.status_code == 200:
            chunks = ""
            if stream:
                # 流式模式：每收到一个 JSON chunk 就解析出 token，累加后 yield ——
                # Gradio 收到一次 yield 就刷新一次聊天框 = 打字机效果
                for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                    if chunk:
                        data = json.loads(chunk)
                        chunks += data.get('answer', '')
                        yield chunks

            else:
                # 非流式模式：收完全部 chunk 才一次性 yield —— 界面等完整答案
                for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                    data = json.loads(chunk)
                    chunks += data.get('answer', '')

                yield chunks

        else:
            # 出错不抛异常 —— 返回文本让聊天框直接显示，用户能看懂
            yield "请求失败，请检查后台服务器是否正常运行。"
    except Exception as e:
        yield f"发生错误：{e}"
