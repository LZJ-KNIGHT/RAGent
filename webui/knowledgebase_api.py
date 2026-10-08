# ============================================================
# knowledgebase_api.py —— 前端知识库页面的"传话筒"
# 每个函数对应知识库页的一个按钮：建库/删库/传文件/列库，
# 都是无业务逻辑的转发 —— 校验后发 HTTP 请求给 kb_routes，把结果显示在界面上
# 返回值用 gr.update(...)：更新提示文字和清空输入框，是 Gradio 的组件更新语法
# ============================================================
import json

import requests
import gradio as gr
import pandas as pd

base_url = "http://127.0.0.1:6605"


# 和 knowledgebase_server/kb_routes.py 的 KB_NAME_ILLEGAL_CHARS 保持一致
KB_NAME_ILLEGAL_CHARS = set('\\/:*?"<>|')


def create_kb(kb_name, kb_info):
    # 前端先做一遍校验给用户即时反馈；后端 normalize_kb_name 会再拦一遍（双保险）
    # 名称为空或含非法字符时直接拦下，不发请求
    kb_name = (kb_name or "").strip()
    if not kb_name:
        return gr.update(value="知识库名称不能为空！", visible=True), gr.update(value=""), gr.update(value="")
    bad = sorted(set(kb_name) & KB_NAME_ILLEGAL_CHARS)
    if bad:
        return gr.update(value=f"知识库名称不能包含这些字符：{' '.join(bad)}", visible=True), gr.update(value=""), gr.update(value="")
    # 定义API的URL
    url = base_url + "/knowledgebase/create_kb"

    # 定义请求数据
    data = {
        "kb_name": kb_name,
        "kb_info": kb_info
    }

    # 发送POST请求
    try:
        response = requests.post(url, json=data)
        # 检查响应状态码
        if response.status_code == 200:
            return gr.update(value="知识库创建成功！", visible=True), gr.update(value=""), gr.update(value="")
        else:
            return gr.update(value=f"知识库创建失败：{response.json().get('detail', '')}", visible=True), gr.update(value=""), gr.update(
                value="")
    except Exception as e:
        return gr.update(value=f"请求失败：{e}", visible=True), gr.update(value=""), gr.update(value="")


def delete_kb(kb_name):
    # 定义API的URL
    url = base_url + "/knowledgebase/delete_kb"

    # 发送POST请求
    try:
        response = requests.delete(url, params={"kb_name": kb_name})
        # 检查响应状态码
        if response.status_code == 200:
            return gr.update(value="知识库删除成功！", visible=True), gr.update(value="")
        else:
            return gr.update(value=f"删除失败：{response.json().get('detail', '')}", visible=True), gr.update(value="")
    except Exception as e:
        return gr.update(value=f"请求失败：{e}", visible=True), gr.update(value="")


def upload_docs(kb_name_upload, file_upload, chunk_size, chunk_overlap):
    # 上传入库入口：文件二进制 + 切块参数一起发 multipart 表单，
    # chunk_size/chunk_overlap 来自界面滑条，后端用它初始化文本切块器
    # 定义 API 的 URL
    upload_docs_url = base_url + "/knowledgebase/upload_docs"  # 请确保端口和路径正确
    # 构建文件和表单数据
    files = [('files', (open(file_path, 'rb'))) for file_path in file_upload]
    data = {
        'kb_name': kb_name_upload,
        'chunk_size': chunk_size,
        'chunk_overlap': chunk_overlap
    }
    # 发送POST请求
    try:
        # 发送 POST 请求
        response = requests.post(upload_docs_url, files=files, data=data)

        # 检查响应状态码并输出结果
        if response.status_code == 200:
            return gr.update(value="文件上传成功", visible=True), gr.update(value=[], visible=False)
        else:
            return gr.update(value=f"文件上传失败，状态码: {response.status_code}, 错误信息: {response.json().get('detail', '')}",
                             visible=True), gr.update(value=[], visible=False)
    except Exception as e:
        return gr.update(value=f"请求失败：{e}", visible=True), gr.update(value=[], visible=False)


def list_kbs():
    # 拉取知识库列表刷新下拉框；把 "西游.faiss" 切成 "西游" 再填进选项
    # 定义API的URL
    list_kbs_url = base_url + "/knowledgebase/list_kbs"  # 请确保端口和路径正确

    # 发送GET请求
    response = requests.get(list_kbs_url)

    # 检查响应状态码并打印结果
    if response.status_code == 200:
        kb_list = response.json()  # 解析JSON格式的知识库列表
        return gr.update(choices=[kb.split(".")[0] for kb in kb_list["knowledgebases"]])
    else:
        return gr.update(choices=[])


# 全局文件列表：记录多选框里已选的文件（模块级全局变量，页面刷新即重置）
selected_files = []


def update(file):
    # 用户在文件选择器里追加选文件时触发：合并去重后回显到界面上
    if file:
        # 将新选中的文件添加到列表中
        for f in file:
            if f not in selected_files:
                selected_files.append(f)
    return gr.update(value=selected_files, visible=True), gr.update(value=[])

