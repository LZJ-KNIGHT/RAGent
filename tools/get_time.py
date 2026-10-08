# ============================================================
# get_time.py —— 时间工具：最简单的一个，无任何外部依赖
# 存在价值：模型本身不知道"现在几点"（训练数据有截止日期，且没有时钟），
# 问"今天几号""现在几点"这类问题时模型必须调它才能答对
# 注意 run 接收 text 参数但不使用 —— 那是框架统一签名的要求，
# 对应 tools_select 里 description 写的"输入应始终为空字符串"
# ============================================================
from datetime import datetime


class Get_time:
    def run(self, text: str):
        # 获取当前时间，格式为 年-月-日 小时:分钟:秒
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return current_time


get_time = Get_time()
