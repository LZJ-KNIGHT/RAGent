# RAGent · 本地知识库 + ReAct Agent 智能助手

一个可本地部署的中文 AI 助手：**多知识库问答 + 联网搜索 + 天气/时间查询 + Python 代码执行**，
由大模型通过 ReAct 循环自主决定调用哪个工具，带 Gradio 图形界面与流式打字机输出。

```
浏览器 ──> webui.py（Gradio 界面，127.0.0.1:7860）
              │  HTTP
              └──> app_server.py（FastAPI 后端，127.0.0.1:6605）
                      ├─ ReAct Agent（LangChain）──> 大模型 / 工具
                      ├─ 知识库服务（FAISS + BM25 混合检索 + SQLite 元数据）
                      └─ /media 静态目录（代码解释器产出的图片）
```

---

## 一、功能特性

| 能力 | 说明 |
| --- | --- |
| 多轮对话 | 中文对话，支持调节 temperature / 历史轮数 / max_tokens / 是否流式 |
| 流式输出 | 自定义回调 + `asyncio.Queue` 逐 token 推送，前端打字机效果 |
| 多知识库管理 | 创建 / 删除知识库，上传并向量化文档，按文件名精确删除 |
| 混合检索 | BM25（jieba 分词）+ FAISS 向量检索，`EnsembleRetriever` 0.5 : 0.5 融合 |
| ReAct 智能体 | 模型自主完成「思考 → 选工具 → 观察结果 → 再思考」循环，最多自主纠错重试 |
| 五个内置工具 | 知识库检索、网络搜索（serpapi）、天气查询、当前时间、Python 代码解释器 |
| 聊天附件 | 上传的文件内容直接并入本轮上下文参与回答 |
| 代码解释器 | 沙箱内执行模型自写的 pandas/matplotlib 代码，生成的图片回显到聊天框 |

**支持的文档格式**：`.txt` `.pdf` `.md` `.csv` `.docx` `.json` `.py`

## 二、技术栈

| 层次 | 选型 |
| --- | --- |
| 前端界面 | Gradio 5.x（ChatInterface + Blocks，两个 Tab） |
| 后端服务 | FastAPI + uvicorn（全异步接口，`StreamingResponse` 流式返回） |
| 智能体框架 | LangChain 0.3（`create_react_agent` + `AgentExecutor`） |
| 对话模型 | Qwen2.5-72B-Instruct（硅基流动，OpenAI 兼容接口） |
| 向量化 | BAAI/bge-large-zh-v1.5（默认在线 API；可切换本地模型，见 §六） |
| 检索 | FAISS（向量）+ BM25（jieba 分词）+ EnsembleRetriever（融合） |
| 存储 | SQLAlchemy + SQLite（知识库元数据）；本地文件（原文 + 向量索引） |
| 代码沙箱 | codeboxapi |
| 文档解析 | pymupdf / python-docx / LangChain loaders |

## 三、目录结构

```
RAGent/
├── app_server.py              后端总入口：创建 FastAPI、挂载路由与 /media 静态目录（6605）
├── webui.py                   前端总入口：Gradio 界面，聊天页 + 知识库管理页（7860）
├── configs/
│   ├── config.template.json   密钥模板 —— 复制为 config.json 后填自己的 key
│   ├── setting.py             全局配置中心：读取密钥 + 各类路径/超时常量
│   └── prompt.py              ReAct 提示词模板（Agent 的行为"剧本"）
├── chat/
│   └── chat_routes.py         聊天接口：组装 prompt → 启动 Agent → 流式返回 token
├── knowledgebase_server/
│   ├── kb_routes.py           知识库接口：建/删/列/上传/删文件/混合检索（在线 embedding）
│   ├── kb_routes_local.py     同一套接口的本地 embedding 版本（备选，见 §六）
│   └── loader/loader.py       按扩展名解析文件为 Document
├── tools/                     Agent 工具集
│   ├── tools_select.py        工具注册表：name / description / func
│   ├── knowledge_search.py    知识库检索（HTTP 回环调用本项目的检索接口）
│   ├── web_search.py          serpapi 联网搜索
│   ├── weather_check.py       心知天气实时天气
│   ├── get_time.py            当前时间
│   └── code_interpreter.py    codebox 沙箱执行 Python，图片落盘到 temp/medias
├── db_server/
│   ├── base.py                SQLAlchemy 引擎 / 会话 / 表定义
│   └── knowledge_base_repository.py   知识库元数据仓储层（增删查）
├── utils/
│   ├── callback.py            流式回调：队列 + 滑动窗口识别 "Final Answer:"
│   ├── load_docs.py           docx / json / py 等文件的读取实现
│   └── downloader.py          可选：下载本地 embedding 模型
├── webui/                     前端侧封装：打包请求参数、转发流式响应
└── static/                    页面静态资源（logo）
```

> 运行时会自动创建 `data/`（原文档）、`knowledgebases/`（FAISS 索引）、`temp/`（临时与图片）、
> `db_server/data/`（SQLite），均已加入 `.gitignore`，无需手动建目录。

## 四、快速开始

### 1. 环境

需要 **Python 3.11**（开发环境实测 3.11.16）。

```bash
pip install -r requirements.txt
```

### 2. 填写密钥（必做）

把模板复制成真实配置文件，再填入自己的 key：

```bash
cp configs/config.template.json configs/config.json    # Windows: copy configs\config.template.json configs\config.json
```

| 字段 | 用途 | 不填会怎样 |
| --- | --- | --- |
| `chat_api_key` | 硅基流动的 key，聊天模型用 | **整个聊天功能不可用** |
| `embedding_api_key` | 硅基流动的 key，向量化用（可与上面同一个） | 建库/上传/检索报错 |
| `serpapi_key` | serpapi 的 key，联网搜索用 | 仅「网络搜索」工具失效 |
| `seniverse_key` | 心知天气的 key，天气查询用 | 仅「天气查询」工具失效 |

`config.json` 已被 `.gitignore` 屏蔽，**不会**进入仓库；仓库里只有空模板。

### 3. 启动（两个进程都要开）

```bash
python app_server.py     # 终端 1：后端，监听 127.0.0.1:6605
python webui.py          # 终端 2：前端，监听 127.0.0.1:7860
```

浏览器打开 <http://127.0.0.1:7860>。

### 4. 使用流程

1. 切到「知识库管理」页 → 填库名与描述 → **创建知识库**
2. 选择知识库 → 上传文件（可调 chunk_size / chunk_overlap）→ **上传并向量化**
3. 回到「聊天机器人」页提问 —— 模型会自行判断是否需要调用知识库检索、联网搜索或代码解释器

## 五、接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/chat/agent_chat` | 智能体对话，流式返回 JSON chunk |
| POST | `/knowledgebase/create_kb` | 创建知识库（建索引 + 元数据登记） |
| DELETE | `/knowledgebase/delete_kb` | 删除知识库（索引目录 + 元数据） |
| GET | `/knowledgebase/list_kbs` | 列出全部知识库 |
| POST | `/knowledgebase/upload_docs` | 上传文件：切块 → 向量化 → 落盘 |
| POST | `/knowledgebase/delete_docs` | 按文件名删除库内文档及其向量片段 |
| POST | `/knowledgebase/search_kb` | 混合检索（供 Agent 的检索工具调用） |
| GET | `/media/*` | 代码解释器产出的图片等静态资源 |

## 六、设计要点

- **Agent 循环与流式输出解耦**：`AgentExecutor` 负责 Thought / Action / Observation 循环；
  自定义 `CallbackHandler` 用 `asyncio.Queue` 把最终答案逐 token 交给前端，滑动窗口识别
  `Final Answer:` 前缀后才开始推送，避免把中间推理过程漏给用户。
- **防幻觉截断**：`stop_sequence=["\nObserv"]` 让模型在写出 Observation 时即被截断，
  工具结果只能由框架填入，模型无法自编工具返回内容。
- **工具错误降级为文本**：工具内部异常会让 Agent 链中断，因此五个工具统一"报错不抛异常"，
  返回可读的错误文本，模型读到后可自行纠正参数或换工具重试。
- **空知识库安全兜底**：检索接口在库为空时直接返回空结果，避免底层检索器构造失败导致 500。
- **双存储一致性**：FAISS 索引（文件系统）与知识库元数据（SQLite）靠库名关联、无跨存储事务，
  删除时按"文件系统 → 数据库"顺序执行并做失败补偿。
- **Windows 中文路径兼容**：faiss 原生接口在含中文的路径上会报错，故对 `faiss.write_index/read_index`
  做了猴子补丁 —— 中文路径先写系统临时目录再搬运。
- **在线 / 本地 embedding 可切换**：默认走硅基流动在线 embedding（免下载模型）；
  想全部本地化时，把 `app_server.py` 中的 `kb_routes` 换成 `kb_routes_local`，
  并 `pip install sentence-transformers torch` 后用 `utils/downloader.py` 下载 BGE 模型。

## 七、已知边界

- 向量检索未设相似度阈值：库里没有相关内容时仍会返回最近邻结果，相关性依赖模型自行判断。
- FAISS 以"整库快照"方式持久化（无增量写、非原子写）：大批量写入期间进程异常可能损坏索引。
- 对话历史保存在进程内存中，重启即清空；无用户体系，`session_id` 仅用于隔离浏览器会话的附件目录。