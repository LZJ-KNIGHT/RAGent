# ============================================================
# utils/callback.py —— 流式输出的"心脏"：LangChain → 前端 的传送带
# 原理：LangChain 每生成一个 token 就回调 on_llm_new_token；
#       本类把 token 过滤后塞进 asyncio.Queue（生产者）；
#       接口层用 aiter() 从队列异步取 token 推给前端（消费者）。
# 两大机制：① 滑动窗口过滤 —— 只放行 Final Answer 之后的 token
#           ② done 事件 —— 保证 aiter 能正常退出、不永久阻塞
# ============================================================
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, List, Literal, Union, cast

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult


# 继承 LangChain 的异步回调基类：框架在"开始生成/每个token/结束/出错"四个时机
# 自动调用对应的 on_xxx 方法，我们只需在各方法里写自己的过滤/放行逻辑
class CustomAsyncIteratorCallbackHandler(AsyncCallbackHandler):
    """Callback handler that returns an async iterator."""

    # token 传送带：生产者是回调（模型token），消费者是 aiter()（前端流）
    queue: asyncio.Queue[str]

    # 结束信号：置位后 aiter() 知道不会再有新 token，可以收尾退出
    done: asyncio.Event

    @property
    def always_verbose(self) -> bool:
        return True

    def __init__(self) -> None:
        self.queue = asyncio.Queue()
        self.done = asyncio.Event()

        # —— 滑动窗口过滤器的三个零件 ——
        # 目标片段：模型说出 "Final Answer:" 之后的内容才是要展示的答案；
        # 之前的 Thought/Action/Action Input 是中间推理，不该进聊天框
        self.answer_prefix_tokens = ["Final", "Answer", ":"]
        self.answer_reached = False
        # 窗口：保存最近 3 个 token（与目标片段等长），用于"即将命中"的比对
        self.last_tokens = [""] * len(self.answer_prefix_tokens)

    # 模型开始新一轮生成时触发。ReAct 多轮循环里模型会被调用多次，
    # 每轮开始都要重置状态：清掉上一轮的结束信号和答案标志，重新开始过滤
    async def on_llm_start(
            self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        # If two calls are made in a row, this resets the state
        self.done.clear()
        self.answer_reached = False #  将answer_reached设置为False
        # print(prompts)

    # 每个 token 产出时触发 —— 滑动窗口过滤的核心：
    # ① token 进窗口，窗口超长就弹出最老的，始终保持最近 3 个
    # ② 窗口[:-1]（最近3个token）与 ["Final","Answer",":"] 完全一致 → 命中
    # ③ 命中后：当前 token 及之后所有 token 全部放行进队列
    # 为什么不在字符串里直接找 "Final Answer:"？—— token 是碎片，
    # 这个词可能被切成 "Fi"+"nal"+" Answer"+":"，拼窗口才能跨碎片识别
    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:

        if token is not None and token != "":
            self.last_tokens.append(token.strip())
            if len(self.last_tokens) > len(self.answer_prefix_tokens) + 1:
                self.last_tokens.pop(0)

            if self.last_tokens[:-1] == self.answer_prefix_tokens:
                self.answer_reached = True

            if self.answer_reached:
                self.queue.put_nowait(token)

    # 一轮生成结束：只有已进入答案阶段才置位 done —— 中间轮次结束时任务还没完，
    # 如果置位会让 aiter 提前退出，流被截断
    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        if self.answer_reached:
            self.done.set()

    # 出错也必须置位 done！否则队列空+done未设 → aiter 永久等待 → 前端卡死转圈
    async def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        self.done.set()

    # 消费者入口：接口层 `async for token in callback.aiter()` 调用它。
    # 退出条件 = 队列空 且 done已置位（生产者明确说没有更多了）。
    # asyncio.wait 同时等两个 future：队列来 token / done 置位，谁先完成处理谁，
    # 输了的那个必须 cancel —— 否则它的 future 挂着不清理，会重复消费
    async def aiter(self) -> AsyncIterator[str]:
        while not self.queue.empty() or not self.done.is_set():
            # Wait for the next token in the queue,
            # but stop waiting if the done event is set
            done, other = await asyncio.wait(
                [
                    # NOTE: If you add other tasks here, update the code below,
                    # which assumes each set has exactly one task each
                    asyncio.ensure_future(self.queue.get()),
                    asyncio.ensure_future(self.done.wait()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel the other task
            if other:
                other.pop().cancel()

            # Extract the value of the first completed task
            token_or_done = cast(Union[str, Literal[True]], done.pop().result())

            # If the extracted value is the boolean True, the done event was set
            if token_or_done is True:
                break

            # Otherwise, the extracted value is a token, which we yield
            yield token_or_done
