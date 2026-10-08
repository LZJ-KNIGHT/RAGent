# ============================================================
# chat_routes.py —— 聊天接口层（Agent 组装车间 + 流式出口）
# 职责：接收前端发来的问题/历史/参数 → 组装 ReAct Agent → 异步执行
#       → 把模型产出的 token 逐个推回前端（打字机效果）
# 数据流：webui打包 --HTTP--> 本文件拆包组装 --> AgentExecutor
#         --> 大模型API/工具 --> callback队列 --> StreamingResponse
# ============================================================
import json
import asyncio
import os
from ast import literal_eval
from fastapi import APIRouter, UploadFile, Form
from fastapi.responses import StreamingResponse
from tools.tools_select import tools
from typing import List, AsyncIterable
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_react_agent, AgentExecutor
from langchain.prompts import SystemMessagePromptTemplate, HumanMessagePromptTemplate
from configs.prompt import PROMPT_TEMPLATES
from configs.setting import chat_model_name, api_key, base_url, TIME_OUT, TEMP_FILE_STORAGE_DIR
from utils.callback import CustomAsyncIteratorCallbackHandler
from db_server.base import session
from db_server.knowledge_base_repository import list_kb_from_db
from tools.code_interpreter import code_interpreter
from utils.load_docs import get_file_content

# 路由组：本文件所有接口的 URL 都以 /chat 开头（如 /chat/agent_chat）。
# tags 只用于 FastAPI 自动生成的接口文档分组；URL 前缀与磁盘文件夹无关
chat_router = APIRouter(prefix="/chat", tags=["Chat 对话"])


def files_rag(files, uuid):
    """处理本次聊天携带的附件：存到 temp/会话id/ 目录，再把全部内容读出拼成字符串。
    注意：这里是"全文直塞"——不切块、不向量化、不检索，属于长上下文方案而非真 RAG，
    拼好的字符串会填进提示词模板的 {documents} 占位符（与知识库检索路径完全不同）。"""
    # 每个会话一个独立子目录（用前端传来的 session_id 命名），互不串文件
    kb_file_storage_path = os.path.join(TEMP_FILE_STORAGE_DIR, uuid)
    result = []
    # 确保存储目录存在
    os.makedirs(kb_file_storage_path, exist_ok=True)
    if files:
        for file in files:
            # 保存文件到指定路径
            file_path = os.path.join(kb_file_storage_path, file.filename)

            with open(file_path, "wb") as f:
                f.write(file.file.read())

    # 遍历目录中的所有文件并读取内容
    for filename in os.listdir(kb_file_storage_path):
        file_path = os.path.join(kb_file_storage_path, filename)
        if os.path.isfile(file_path):
            file_content = get_file_content(file_path)

            # 直接将路径和内容拼接到结果字符串
            result.append(f"document:.{file_path}\ncontent:{file_content}\n")
    return "".join(result)


# 聊天主接口。下面每个 Form(...) 都是"收货声明"：
# 字段名必须和 webui/chat_with_agent_api.py 打包 data 里的 key 一一对应，
# 对不上不会报错、后端只会静默用默认值 —— 排查参数问题先对两边字段名
@chat_router.post("/agent_chat")
async def agent_chat(
        files: List[UploadFile] = None,
        query: str = Form(..., description="用户输入"),
        sys_prompt: str = Form("You are a helpful assistant.", description="系统提示"),
        history_len: int = Form(-1, description="保留历史消息的数量"),
        history: List[str] = Form([], description="历史对话"),
        temperature: float = Form(0.5, description="LLM采样温度"),
        max_tokens: int = Form(1024, description="LLM最大token数配置"),
        session_id: str = Form(None, description="会话标识"),
):
    # 附件内容字符串（无附件时为空串），稍后填进模板的 {documents}
    documents = files_rag(files, session_id)
    # 前端传来的是字符串形式的 dict（如 "{'role':'user',...}"），
    # literal_eval 安全地把它还原成真正的 dict 对象
    history = [literal_eval(item) for item in history]
    # 截断历史：1 轮 = 一问一答 = 2 条消息，所以按 2*轮数 截取尾部；
    # history_len=-1 表示不截断（保留全部）
    histories = ""
    if history_len > 0:
        history = history[-2 * history_len:]

    # 把历史拼成纯文本填进模板的 {history} —— 模型靠这段"回忆"接上文
    for msg in history:
        role = msg.get('role')
        content = msg.get('content')
        histories += f"{role}:{content}\n\n"

    # 真正干活的生成器：Agent 在这里跑，token 从这里流回前端。
    # 定义成内嵌函数是为了闭包住外层解析好的 query/history 等局部变量
    async def agent_chat_iterator() -> AsyncIterable[str]:
        # 自定义回调：模型每产出一个 token 就推给它，它放进队列；
        # 本函数再从队列取出并 yield —— 相当于生产者-消费者之间的传送带
        callback = CustomAsyncIteratorCallbackHandler()
        callbacks = [callback]

        # 聊天模型客户端：OpenAI SDK 兼容写法，base_url 指向硅基流动所以实际调它。
        # streaming=True 是流式前提（token 逐个产出才会触发回调）；
        # temperature/max_tokens 来自前端滑条，每个请求独立实例互不影响
        chat_model = ChatOpenAI(
            model=chat_model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True,
            callbacks=callbacks
        )

        # 定义系统提示，用于设置行为规则
        system_prompt = SystemMessagePromptTemplate.from_template(
            sys_prompt
        )

        # 定义人类提示，用于用户输入
        human_prompt = HumanMessagePromptTemplate.from_template(
            PROMPT_TEMPLATES["agent"]
        )
        # 组装成完整的 ChatPromptTemplate
        chat_prompt = ChatPromptTemplate.from_messages([system_prompt, human_prompt])

        # 组装 ReAct Agent：模板要求模型按 Thought/Action/Action Input 格式输出。
        # stop_sequence="\nObserv" 是防幻觉关键：模型一写到 Observation 就被截断，
        # 它无法伪造工具结果 —— Observation 只能由框架执行工具后填入 scratchpad
        agent = create_react_agent(chat_model, tools, chat_prompt, stop_sequence=["\nObserv"])
        agent_executor = AgentExecutor.from_agent_and_tools(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=True,
        )

        # 从 SQLite 查出所有知识库，拼成"菜单"文本填进 {knowledgebases}。
        # 模型全靠这段描述决定查哪个库 —— kb_info 写得越准，路由越准
        knowledgebases = list_kb_from_db(session)
        kbs = "".join([f"{kb['kb_name']} - {kb['kb_info']} \n" for kb in knowledgebases])
        code_interpreter.output_files, code_interpreter.output_codes = "", ""
        # create_task 把 Agent 扔到后台协程异步跑（不阻塞当前生成器），
        # 这样下面的 aiter() 才能立刻开始消费 token —— 这是流式不卡白屏的关键。
        # 顺序注意：create_task 必须在 add_done_callback 之前拿到 task 引用
        task = asyncio.create_task(
            agent_executor.acall(
                inputs={"input": query, "history": histories, "knowledgebases": kbs, "documents": documents})
        )
        # 兜底：agent 无论正常结束还是抛异常，都要让 callback 的 done 事件置位。
        # 否则下面 aiter() 的 while 条件是「队列空 and done 未设置」→ 永久阻塞，
        # 前端一直转圈，连 TIME_OUT 都执行不到（wait_for 在 aiter 之后）。
        task.add_done_callback(lambda _: callback.done.set())

        # 流式输出：从队列逐个取 token 包成 JSON 推给前端（打字机效果的源头）；
        # 循环退出的条件是"队列空且 done 已置位"（见 callback.aiter 的实现）
        async for token in callback.aiter():
            response_data = {
                "answer": token,
            }
            yield json.dumps(response_data).encode('utf-8')

        # 双保险收尾：① 流结束后再 await task，确认 Agent 真正跑完；
        # ② 前面的 add_done_callback 已兜底置位 done，这里即使 Agent 内部炸了
        #    也能拿到异常，把原因写进聊天框 —— 而不是让前端看到流静默中断
        try:
            await asyncio.wait_for(task, TIME_OUT)
        except asyncio.TimeoutError:
            yield json.dumps({"answer": f"\n\n[执行超时] Agent 运行超过 {TIME_OUT} 秒，已中断。"}).encode('utf-8')
            return
        except Exception as e:
            yield json.dumps({"answer": f"\n\n[执行出错] {type(e).__name__}: {e}"}).encode('utf-8')
            return
        # 取 code_interpreter 产生的图表文件路径和本次执行代码（全局单例上暂存的）
        output_files, output_codes = code_interpreter.get_outputs()

        # 把画图结果发给前端：有图片时拼成 Markdown 图片语法，前端渲染后
        # 直接显示在聊天框里；图片 URL 指向 app_server 挂载的静态目录 /media
        if output_files:
            yield json.dumps({"answer": f'\n\n{output_codes}\n\n![](http://localhost:6605{output_files})'}).encode(
                'utf-8')
        else:
            yield json.dumps({"answer": f'\n\n{output_codes}'}).encode('utf-8')

    # StreamingResponse：把生成器交给框架，每 yield 一段就立刻推给前端一个
    # HTTP chunk —— 这就是"打字机效果"在网络层的实现
    return StreamingResponse(agent_chat_iterator(), media_type="application/json")
