# ============================================================
# configs/prompt.py —— ReAct 提示词模板（Agent 的"剧本"）
# 这是整个项目最核心的一段配置：模型按这个格式决定何时调工具。
# 大括号占位符由 chat_routes/AgentExecutor 在运行时填充：
#   {tools}           工具清单（tools_select 里每个 Tool 的 name+description）
#   {knowledgebases}  知识库菜单（SQLite 查出的"库名 - 描述"）
#   {documents}       聊天附件全文（files_rag 拼的字符串，伪 RAG 直塞）
#   {tool_names}      只有工具名，用于约束 Action 的取值范围
#   {history}         历史对话文本
#   {input}           本轮用户问题
#   {agent_scratchpad} 中间推理区：Thought/Action/Observation 逐轮累积，
#                      上一轮工具的真实结果就在这里喂回给模型
# 格式约定最后落在 "Final Answer:" —— callback.py 的滑动窗口就盯着这个词放行
# ============================================================
PROMPT_TEMPLATES = {
    "agent":   'Answer the following questions as best you can. If it is in order, you can use some tools and knowledgebases '
               'appropriately. '
               'You have access to the following tools:\n\n'
               '{tools}\n\n'
               'You have access to the following knowledge bases:\n\n'
               '{knowledgebases}\n\n'
               # {documents} 是后端预读好的附件全文。下面两句是"防走偏护栏" ——
               # 不加的话，模型看到文件名就绕开现成内容，自己用工具去打开文件
               'You have the following documents (full contents of the user-uploaded attachments, already extracted for you):\n\n'
               '{documents}\n\n'
               'Never open, read, extract or download these files yourself — do not use code_interpreter or web search '
               'to read local files, their contents are already provided above. '
               'If a document is empty or cannot be parsed, just tell the user directly.\n\n'
               'Use the following format:\n'
               'Question: the input question you must answer\n'
               'Thought: you should always think about what to do and what tools to use.\n'
               'Action: the action to take, should be one of [{tool_names}]\n'
               'Action Input: the input to the action\n'
               # Observation 这一行模型只能照抄格式、不能编内容 ——
               # chat_routes 的 stop_sequence="\nObserv" 会在它开写时截断
               'Observation: the result of the action\n'
               '... (this Thought/Action/Action Input/Observation can be repeated zero or more times)\n'
               'Thought: I now know the final answer\n'
               'Final Answer: the final answer to the original input question\n'
               'Begin!\n\n'
               'History: {history}\n\n'
               'Question: {input}\n\n'
               'Thought: {agent_scratchpad}\n',
}