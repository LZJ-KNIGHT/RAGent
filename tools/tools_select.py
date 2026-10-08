# ============================================================
# tools_select.py —— 工具注册表：Agent 的"工具箱清单"
# 职责：把五个工具类实例统一包装成 LangChain 的 Tool 对象，汇成 tools 列表。
# chat_routes.py 里 create_react_agent(chat_model, tools, ...) 拿的就是这个列表。
# 每个工具对模型暴露两样东西：name（Action 里写的名字）和
# description（模型判断"该不该用这工具、输入什么格式"的唯一依据）
# —— description 写得差，模型就会用错工具或传错参数，比代码 bug 更致命
# ============================================================
from langchain_core.tools import Tool, StructuredTool
from tools.code_interpreter import code_interpreter
from tools.weather_check import weather_check
from tools.web_search import web_search
from tools.knowledge_search import knowledgebas_search
from tools.get_time import get_time

# 将API工具封装成Langchain的Tool对象：
# name    —— ReAct 输出里 Action: 后面跟的名字（模型照抄，改动会直接断链）
# func    —— 传的是各实例的 run 方法（函数引用，框架自动把 Action Input 传进去）
# description —— 会拼进提示词的 Tools 区，模型靠它做工具选择决策
tools = [
    Tool(
        name="weather check",
        func=weather_check.run,
        description="获取当前地点或指定城市的实时天气信息，包括温度、天气状况等。"
    ),

    Tool(
        name="web search",
        func=web_search.run,
        description="通过网络搜索获取最新资讯、回答问题或查找特定主题的相关内容。"
    ),

    Tool(
        name="knowledge search",
        func=knowledgebas_search.run,
        # 这段 description 额外规定了输入格式 '库名,问题' ——
        # 模型正是读了它，才知道要自己把库名拼在问题前面
        description="搜索本地知识库，获取与特定主题相关的内容。此工具的输入应是一个由 ',' 分隔的两个字符串，第一个字符串表示您需要查询的知识库，第二个字符串表示您需要查询的问题。例如，您想要在 '人工智能' 知识库查询关于 '人工智能学习方法' ，输入应为 '人工智能,人工智能学习方法' 。"
    ),

    Tool(
        name="get time",
        func=get_time.run,
        description="获取当前时间。输入应始终为空字符串"
    ),

    Tool(
        name="code interpreter",
        func=code_interpreter.run,
        description="一个Python shell。使用它来执行python代码。输入应该是一个有效的python代码字符串。在与开头引号相同的行开始编写代码。不要以换行开始你的代码。"
    ),
]
