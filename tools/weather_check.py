# ============================================================
# weather_check.py —— 天气查询工具
# 五个工具里最简单的"直接型"工具：逻辑全在自己内部，
# 拿城市名调心知天气第三方 API，拼成一句话返回给模型当 Observation
# ============================================================
import requests
from pydantic import Field
from configs.setting import TIME_OUT, seniverse_key

class WeatherCheck:
    city: str = Field(description="City name,include city and county")

    def __init__(self, api_key):
        self.api_key = api_key

    def run(self, city):
        # 模型的 Action Input 可能带换行（多行输入时），只取第一行当城市名，
        # 否则带换行的城市名拼进 URL 会让第三方 API 报错
        city = city.split('\n')[0]  # 清除多余的\n不然API会报错。
        url = f"https://api.seniverse.com/v3/weather/now.json?key={self.api_key}&location={city}&language=zh-Hans&unit=c"
        # 发送请求到心知天气API
        # print(url)
        response = requests.get(url, timeout=TIME_OUT)
        # print(response.status_code)
        # 如果请求成功，解析返回数据
        if response.status_code == 200:
            data = response.json()
            # 获取天气信息
            weather = data['results'][0]['now']['text']
            temperature = data['results'][0]['now']['temperature']
            return f"{city}的天气是{weather}，温度为{temperature}°C"
        else:
            # 失败不抛异常、只返回错误文本 —— 和 knowledge_search 同一原则：
            # 工具异常会穿透 AgentExecutor 中断整条链，返回文本则模型能自己理解并纠正
            return f"错误码: {response.status_code}, 无法获取{city}的天气信息"

# 模块级实例，seniverse_key 在 configs/setting.py 统一从 config.json 读取
weather_check = WeatherCheck(seniverse_key)