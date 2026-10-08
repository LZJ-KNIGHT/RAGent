# ============================================================
# code_interpreter.py —— Python 代码执行工具（画图能力的来源）
# 职责：接收模型生成的 Python 代码 → 交给 codebox 沙箱远程执行
#       → 若产出图片则存盘并把 URL 记在实例属性上，
#         由 chat_routes 在流结束后取出拼进聊天框显示
# 设计要点：模块底部创建全局单例 code_interpreter ——
#         chat_routes 每次请求前重置它的 output_files/output_codes，
#         流结束后再 get_outputs() 取回，靠这个全局变量在两层之间传结果
# ============================================================
import base64
import os
import re
from uuid import uuid4
from codeboxapi import CodeBox
from configs.setting import MEDIA_DIR


class CodeInterpreter:
    def __init__(self):
        self.output_files = ""
        self.output_codes = ""
        self.codebox = CodeBox(api_key="local")
        self.codebox.start()

    # 添加获取 output_files 的方法
    def get_outputs(self):
        return self.output_files, self.output_codes

    def run(self, code: str):
        # 第一步：清洗代码。模型输出常带 ```python 代码块标记，直接执行会语法错误，
        # 用正则把三种可能的围栏（```python / ```py / ```）全部去掉
        clean_code = re.sub(r'(```python|```py|```)\s*', '', code, flags=re.IGNORECASE)
        # 去除首尾的空白字符
        clean_code = clean_code.strip()
        # 去除多余的空行
        lines = [line for line in clean_code.split('\n') if line.strip()]
        # 将处理后的行重新组合成字符串
        cleaned_code = '\n'.join(lines)

        # 第二步：交给 codebox 沙箱执行 —— 代码不在本进程跑！
        # 好处：模型生成的代码不可信，沙箱隔离了误删文件、死循环等风险
        output = self.codebox.run(cleaned_code)

        # 第三步：判断产出类型。matplotlib 画图时 codebox 返回的是 base64 编码的 PNG
        if output.type == "image/png":
            # 用 uuid4 随机命名防覆盖，存到 temp/medias（app_server 已把它挂载到 /media 路由）
            filename = f"{MEDIA_DIR}/image-{uuid4()}.png"
            decoded_image = base64.b64decode(output.content)

            # 将解码后的数据写入文件
            with open(filename, 'wb') as file:
                file.write(decoded_image)

            # 生成图片的URL
            # 把图片 URL 和用户代码暂存在实例属性上 ——
            # 本函数的返回值只会作为 Observation 给模型看，前端看不到；
            # 真正把图发给前端的是 chat_routes 在流结束后调 get_outputs() 取走这两样
            image_url = f"/media/{os.path.basename(filename)}"
            self.output_files = image_url
            self.output_codes = code

            # 告诉模型"图已交付"，模型就知道任务完成可以写 Final Answer 了
            return f"Image got send to the user."
        else:
            # 非图片输出（print 结果、报错信息等）原样返回 ——
            # 报错信息给到模型很重要：它会读报错自己改代码重试，这是自修复能力
            return output.content


# 全局单例：tools_select.py 注册的是这个实例的 run 方法，
# chat_routes.py 读写的是同一个实例的 output 属性 —— 三方共享同一份状态
code_interpreter = CodeInterpreter()
