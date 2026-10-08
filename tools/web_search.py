# ============================================================
# web_search.py —— 网络搜索工具
# 职责：把模型给的关键词发给 serpapi（百度引擎），把搜索结果的
#       标题/链接/摘要 拼成文本返回给模型当 Observation
# 让模型能回答"最新资讯"类问题 —— 训练数据之外的知识全靠它和知识库补
# ============================================================
import requests
from pydantic import Field
from configs.setting import TIME_OUT, serpapi_key

class WebSearch:
    query: str = Field(description="需要网上查找的内容")

    def __init__(self, api_key):
        # 初始化函数，用于创建类的实例
        self.api_key = api_key

    def run(self, query):
        base_url = "https://serpapi.com/search"

        params = {
            "q": query,
            "api_key": self.api_key,
            "engine": "baidu",   # serpapi 是聚合网关，这里选百度作为底层搜索引擎
            "rn": 5,             # 只要前 5 条结果 —— 够模型用又不撑爆上下文
        }

        # 发送请求到网络搜索API
        response = requests.get(base_url, params=params, timeout=TIME_OUT)

        # 双重错误检查之一（HTTP层）：状态码非 200（最常见 429 额度用尽），
        # 把原始错误说明带出来方便排查，同时返回文本给模型而不是抛异常
        if response.status_code != 200:
            try:
                reason = response.json().get("error", "")
            except ValueError:
                reason = response.text[:100]
            return f"无法获取{query}的信息（serpapi 返回 {response.status_code}: {reason}）"

        data = response.json()

        # 双重错误检查之二（业务层）：serpapi 也可能返回 200 但响应体里带 error 字段
        if "error" in data:
            return f"无法获取{query}的信息（serpapi 返回: {data['error']}）"

        # organic_results 是搜索结果主体；百度引擎有时把结果挂在
        # 第一条的 related_news 字段下，做一次兼容提取
        organic_results = data.get("organic_results", [])
        if organic_results and organic_results[0].get("related_news"):
            organic_results = organic_results[0]["related_news"]

        if not organic_results:
            return f"未搜索到与{query}相关的结果"

        # 拼成 结构化文本（标题/链接/摘要 三段式）——
        # 模型读这种格式比读原始 JSON 更省 token 也更准
        results = "".join([f"titles:\n{result.get('title', '')} \nlinks:\n{result.get('link', '')}\nsnippets:\n{result.get('snippet', '')}\n" for result in organic_results])
        return results


# 模块级实例，api_key 在 configs/setting.py 统一管理
web_search = WebSearch(serpapi_key)
