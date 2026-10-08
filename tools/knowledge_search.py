# ============================================================
# knowledge_search.py —— 知识库检索工具（五个工具里唯一"自己不干活"的）
# 职责：解析模型给的 '库名,问题' 格式字符串 → HTTP 回环调用
#       本后端(6605)的 /knowledgebase/search_kb 接口 → 把结果拼成文本返回
# 为什么绕 HTTP 而不直接 import 检索函数？
#   ① 工具层与检索层解耦：检索将来独立部署，工具代码零改动
#   ② 白嫖接口层现成的校验防御（404/空库/格式错误）
#   ③ 前端网页和 Agent 共用同一个检索入口，行为只有一条路径
# ============================================================
import json

import requests
from pydantic import Field
from configs.setting import TIME_OUT

# 知识库搜索工具类
class KnowledgeBaseSearch:
    inputs: str = Field(description="包含知识库名称和需要查询问题的字符串")

    def run(self, inputs):
        # 工具出错必须返回文本让模型自己纠正，不能抛异常 ——
        # AgentExecutor 不会捕获工具的异常，抛出去会直接中断整条链。
        # 第一道防御：没有逗号说明模型没按格式写 —— 此时不抛异常，
        # 而是返回一段格式纠错提示。模型读到后会自动按正确格式重试
        if not inputs or "," not in inputs:
            return ("输入格式错误：应为 '知识库名,问题' 两段，用英文逗号分隔，"
                    "例如 'test,黑熊精是谁'。可用的知识库名称已经在提示中列出，请直接使用。")
        # maxsplit=1 只切第一个逗号：问题本身带逗号时（'test,黑熊精是谁,他住哪'）
        # 后半段整体算问题，不会把问题切碎
        kb_name, query = inputs.split(",", 1)
        kb_name, query = kb_name.strip(), query.strip()
        if not kb_name or not query:
            return "输入格式错误：知识库名和问题都不能为空，格式为 '知识库名,问题'。"
        # 127.0.0.1:6605 = 本项目自己的后端 —— HTTP 回环（自己请求自己）
        url = "http://127.0.0.1:6605/knowledgebase/search_kb"

        # 请求体：两个 key 与 kb_routes.search_kb 的 Body 声明一一对应
        data = {
            "kb_name": kb_name,
            "query": query
        }

        # 将数据转换为JSON格式
        json_data = json.dumps(data)

        # 设置请求头，指定发送的数据格式为JSON
        headers = {
            'Content-Type': 'application/json'
        }

        # 发送POST请求
        response = requests.post(url, data=json_data, headers=headers, timeout=TIME_OUT)

        # 成功：把 [{sources,page_contents},...] 拼成 "来源+原文" 结构化文本。
        # 这个返回值会作为 Observation 塞回给模型 —— 模型就是读着它写 Final Answer
        if response.status_code == 200:
            data = response.json()

            # 获取知识库信息
            res = "".join([f"source:\n{d['sources']} \ncontext:\n{d['page_contents']}\n" for d in data['results']])
            return res
        else:
            # 失败（库不存在 404 / 空库等）：返回错误文本让模型自行决断，
            # 不抛异常 —— 异常会穿透 AgentExecutor 中断整条对话链
            return f"无法获取和{query}有关信息"


knowledgebas_search = KnowledgeBaseSearch()
# 使用示例
# print(database_search.run("hqyj,黑熊精自称"))
