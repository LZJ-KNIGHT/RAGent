# ============================================================
# webui.py —— 前端总入口（Gradio 界面，默认 7860 端口）
# 两个 Tab：聊天机器人（ChatInterface + 侧栏参数滑条）
#           知识库管理（建库/删库/上传向量化）
# 本文件只负责"摆界面 + 绑按钮"：所有事件处理都转发给
# webui/chat_with_agent_api.py 和 webui/knowledgebase_api.py 两个模块
# 启动顺序：先 python app_server.py（后端6605）→ 再 python webui.py（前端7860）
# ============================================================
import os
import uuid
import gradio as gr
from webui.chat_with_agent_api import chat_with_agent
from webui.knowledgebase_api import create_kb, delete_kb, upload_docs, list_kbs, update

# 让 static/ 目录下的文件可以被页面引用（下面的 logo 图片）。
# 必须在 gr.Blocks() 之前调用，引用的 URL 形如 /gradio_api/file=static/xxx.png。
gr.set_static_paths(paths=["static"])

LOGO_SRC = "/gradio_api/file=static/logo.png"
# 标题用 gr.HTML 而不是 gr.Markdown：Markdown 会把 <img> 当成独立的一块渲染，
# logo 会掉到"聊天机器人"上面去，flex 排一下才能并排。
CHAT_TITLE = (
    '<h2 style="display:flex;align-items:center;gap:10px;margin:0;">'
    f'<img src="{LOGO_SRC}" alt="logo" style="height:44px;width:44px;object-fit:contain;">'
    '<span>聊天机器人</span></h2>'
)

# 页脚整条（"通过 API 使用 · 使用 Gradio 构建 · 设置"）隐藏掉，聊天页和知识库页都不显示。
# 注意：隐藏的是按钮本身，设置弹窗仍然可用——左侧栏的「设置」按钮会去点一下这个被隐藏的按钮。
# .icon-button-wrapper.top-panel 是聊天区右上角那个垃圾桶（内置的"清空对话"）的外层容器，
# 左侧栏已经有自己的清空按钮了，这个就藏起来，避免出现两个。
CUSTOM_CSS = """
footer { display: none !important; }
.icon-button-wrapper.top-panel { display: none !important; }
"""

# 点左侧栏「设置」时，去点页脚里那个已被 CSS 隐藏的设置按钮，把设置弹窗打开。
# display:none 的元素一样能收到程序化的 .click()。
JS_OPEN_SETTINGS = """
() => {
    const btn = document.querySelector('footer button.settings');
    if (btn) btn.click();
}
"""


class NamedFileChatbot(gr.Chatbot):
    """让附件在聊天记录里只显示文件名，而不是一长串临时路径。

    gradio 的 ChatInterface 把附件写进历史时用的是 {"content": (path,)}（1 元组），
    Chatbot 渲染成 FileMessage 时 alt_text 为空，前端就只能把 path 原样显示出来。
    改成 2 元组 (path, 文件名) 后，_get_alt_text 会取第二个元素作为显示名。

    只影响显示：传给后端的数据没有被改，open() 拿到的仍然是完整路径。
    注意：依赖 Chatbot._postprocess_content 这个私有方法，gradio 大版本升级要复查。
    """

    # 关键：不加这行，gradio 会按类名把本类注册成一个全新组件类型 "namedfilechatbot"，
    # 前端 JS 里没有这个组件，整个页面会永远停在「加载中」。
    # 设了 is_template，blocks.py 的 get_block_name() 就返回父类名，前端按 Chatbot 渲染。
    is_template = True

    def _postprocess_content(self, chat_message):
        if (
            isinstance(chat_message, tuple)
            and len(chat_message) == 1
            and isinstance(chat_message[0], str)
        ):
            chat_message = (chat_message[0], os.path.basename(chat_message[0]))
        return super()._postprocess_content(chat_message)


# 定义一个生成唯一会话 ID 的函数
def generate_session_id():
    return str(uuid.uuid4())


# 在 Gradio 应用加载时生成新的会话ID
def on_app_load():
    session_id = generate_session_id()
    return session_id


with gr.Blocks(fill_width=True, fill_height=True, css=CUSTOM_CSS) as demo:
    # 使用 on_load 事件来生成会话ID
    session_state = gr.State(value=on_app_load)

    with gr.Tab("聊天机器人"):
        gr.HTML(CHAT_TITLE)

        with gr.Row():
            with gr.Column(scale=1, variant="panel") as sidebar_left:
                # visible=False：系统提示语不该给用户看，但组件本身要留着，
                # ChatInterface 靠它把值作为 additional_input 传给后端。
                sys_prompt = gr.Textbox(visible=False, value="你是用户的专属聊天机器人，请始终使用中文回答。当用户询问你是谁、你叫什么名字、你是什么模型、由谁开发时，只回答「我是您的专属聊天机器人」，不要提及任何底层模型或公司的名称。")
                history_len = gr.Slider(minimum=-1, maximum=10, value=1, step=1, label="保留历史对话轮数（-1 = 全部）")
                temperature = gr.Slider(minimum=0.01, maximum=2.0, value=0.5, step=0.01, label="temperature")
                max_tokens = gr.Slider(minimum=64, maximum=1024, value=512, step=8, label="max_length")
                stream = gr.Checkbox(label="stream", value=True)
                with gr.Row():
                    settings_button = gr.Button("⚙️ 设置")
                    clear_button = gr.Button("🗑️ 清空对话")

            with gr.Column(scale=10) as main:
                chatbot = NamedFileChatbot(height=600, type="messages", )
                chat_interface = gr.ChatInterface(fn=chat_with_agent,
                                                  multimodal=True,
                                                  type="messages",
                                                  theme="soft",
                                                  chatbot=chatbot,
                                                  additional_inputs=[
                                                      sys_prompt,
                                                      history_len,
                                                      temperature,
                                                      max_tokens,
                                                      stream,
                                                      session_state,  # 使用 session_state 组件来传递会话ID
                                                  ],
                                                  )

        # 「设置」只是转发给页脚里被隐藏的那个设置按钮，没有任何 Python 逻辑。
        settings_button.click(fn=None, inputs=None, outputs=None, js=JS_OPEN_SETTINGS)

        # 「清空对话」要同时清两个地方，否则清完界面是空的、但模型还记得上下文：
        #   chatbot                 —— 界面上显示的消息
        #   chat_interface.chatbot_state / chatbot_value —— ChatInterface 内部真正喂给模型的历史
        clear_button.click(fn=lambda: ([], [], []),
                           inputs=None,
                           outputs=[chatbot, chat_interface.chatbot_state, chat_interface.chatbot_value],
                           show_api=False,
                           queue=False)

    # 知识库操作页
    with gr.Tab("知识库管理"):
        gr.Markdown("## 📚 知识库管理")
        gr.Markdown("请先输入名字与描述创建知识库后再上传文件并向量化~")

        with gr.Row():
            kb_name = gr.Textbox(label="知识库名称", placeholder="请输入知识库名称")
        with gr.Row():
            kb_info = gr.Textbox(label="知识库描述", placeholder="请输入知识库描述")
        with gr.Row():
            # 隐藏的消息框，用于显示操作结果
            message_box = gr.Markdown(visible=False)
        with gr.Row():
            create_button = gr.Button("创建知识库")
            delete_button = gr.Button("删除知识库")

        kbs = list_kbs()['choices']
        with gr.Row():
            kb_name_upload = gr.Dropdown(label="选择知识库", choices=kbs)
        with gr.Row():
            file_uploaded = gr.Files(label="已选择的文件", visible=False)
        with gr.Row():
            file_upload = gr.Files(label="选择文件")
        with gr.Row():
            chunk_size = gr.Number(label="知识库中单段文本最大长度(chunk_size)", value=128, minimum=1, maximum=800)
            chunk_overlap = gr.Number(label="知识库中相邻文本重合长度(chunk_overlap)", value=20, minimum=0, maximum=400)
        with gr.Row():
            upload_button = gr.Button("上传并向量化")
        with gr.Row():
            # 隐藏的消息框，用于显示操作结果
            upload_message_box = gr.Markdown(visible=False)

        # 按钮事件绑定模式：click(处理函数, 输入组件列表, 输出组件列表)，
        # .then(...) 是链式事件 —— 上一步完成后自动刷新知识库下拉框
        create_button.click(create_kb, [kb_name, kb_info], [message_box, kb_name, kb_info]).then(fn=list_kbs,
                                                                                                 outputs=kb_name_upload)

        delete_button.click(delete_kb, [kb_name_upload], [message_box, kb_name]).then(fn=list_kbs, outputs=kb_name_upload)

        file_upload.upload(fn=update, inputs=[file_upload], outputs=[file_uploaded, file_upload])

        upload_button.click(upload_docs, [kb_name_upload, file_uploaded, chunk_size, chunk_overlap],
                            [upload_message_box, file_uploaded])

# 启动应用
demo.launch()
