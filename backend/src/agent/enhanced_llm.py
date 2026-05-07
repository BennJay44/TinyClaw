"""增强版 HelloAgentsLLM - 支持流式工具调用"""

import os
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Union, Any, AsyncIterator

from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.core.exceptions import HelloAgentsException


# ==================== 流式工具调用数据结构 ====================

class StreamToolEventType(Enum):
    """流式工具调用事件类型"""
    CONTENT = "content"  # 文本内容增量
    TOOL_CALL_START = "tool_call_start"  # 工具调用开始（收到ID和名称）
    TOOL_CALL_DELTA = "tool_call_delta"  # 工具调用参数增量
    FINISH = "finish"  # 流结束


@dataclass
class StreamToolEvent:
    """流式工具调用事件

    封装流式响应中的不同类型数据，统一处理文本内容和工具调用。
    """
    event_type: StreamToolEventType
    # 文本内容
    content: Optional[str] = None
    # 工具调用
    tool_call_index: Optional[int] = None  # 工具调用索引（用于增量累积）
    tool_call_id: Optional[str] = None  # 工具调用ID
    tool_name: Optional[str] = None  # 工具名称
    tool_arguments_delta: Optional[str] = None  # 参数增量
    # 结束信息
    finish_reason: Optional[str] = None

    @property
    def is_content(self) -> bool:
        """是否为文本内容事件"""
        return self.event_type == StreamToolEventType.CONTENT

    @property
    def is_tool_call(self) -> bool:
        """是否为工具调用事件"""
        return self.event_type in (
            StreamToolEventType.TOOL_CALL_START,
            StreamToolEventType.TOOL_CALL_DELTA
        )

    @property
    def is_finish(self) -> bool:
        """是否为结束事件"""
        return self.event_type == StreamToolEventType.FINISH


@dataclass
class StreamToolCallResult:
    """流式工具调用完成后的结果

    包含累积的文本内容和工具调用列表。
    """
    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: Optional[str] = None

    def add_content(self, delta: str):
        """添加文本内容"""
        self.content += delta

    def add_tool_call_start(self, index: int, tool_id: str, tool_name: str):
        """添加工具调用开始"""
        # 确保列表足够长
        while len(self.tool_calls) <= index:
            self.tool_calls.append({"id": "", "name": "", "arguments": ""})
        self.tool_calls[index]["id"] = tool_id
        self.tool_calls[index]["name"] = tool_name

    def add_tool_call_delta(self, index: int, arguments_delta: str):
        """添加工具调用参数增量"""
        while len(self.tool_calls) <= index:
            self.tool_calls.append({"id": "", "name": "", "arguments": ""})
        self.tool_calls[index]["arguments"] += arguments_delta

    def get_complete_tool_calls(self) -> List[Dict[str, Any]]:
        """获取完整的工具调用列表（过滤不完整的）"""
        return [
            tc for tc in self.tool_calls
            if tc["id"] and tc["name"]
        ]

    def to_assistant_message(self) -> Dict[str, Any]:
        """转换为助手消息格式（用于追加到消息历史）"""
        message: Dict[str, Any] = {"role": "assistant", "content": self.content or None}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"]
                    }
                }
                for tc in self.get_complete_tool_calls()
            ]
        return message


# ==================== 增强版 LLM 类 ====================

class EnhancedHelloAgentsLLM(HelloAgentsLLM):
    """
    增强版 HelloAgentsLLM - 添加流式工具调用支持

    继承自 HelloAgentsLLM，新增以下方法：
    - astream_invoke_with_tools: 异步流式工具调用
    - get_last_stream_tool_result: 获取最后一次流式工具调用的累积结果
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_stream_tool_result: Optional[StreamToolCallResult] = None

    async def astream_invoke_with_tools(
        self,
        messages: List[Dict],
        tools: List[Dict],
        tool_choice: Union[str, Dict] = "auto",
        **kwargs
    ) -> AsyncIterator[StreamToolEvent]:
        """
        异步流式调用 LLM 并支持工具调用（Function Calling）

        使用 httpx 直接调用 API，绕过 openai 库在 Windows uvicorn 环境下的连接问题。

        Args:
            messages: 消息列表
            tools: 工具 schema 列表
            tool_choice: 工具选择策略
            **kwargs: 其他参数（temperature, max_tokens 等）

        Yields:
            StreamToolEvent: 流式事件，可能是文本内容或工具调用增量
        """
        import asyncio
        import httpx

        # 构建请求参数
        request_body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "stream": True,
        }
        if kwargs.get("temperature") is not None:
            request_body["temperature"] = kwargs["temperature"]
        if self.max_tokens:
            request_body["max_tokens"] = self.max_tokens

        # 初始化累积结果
        result = StreamToolCallResult()

        # 使用队列在线程中运行同步流式调用
        _SENTINEL = object()
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        base_url = self.base_url
        if base_url and not base_url.startswith(("http://", "https://")):
            base_url = f"https://{base_url}"
        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        def _stream_worker():
            """在线程中运行 httpx 流式调用，将事件放入队列"""
            print(f"[DEBUG] LLM请求: {url}, messages={len(request_body.get('messages',[]))}, tools={len(request_body.get('tools',[]))}")
            try:
                with httpx.Client(
                    transport=httpx.HTTPTransport(retries=2),
                    timeout=httpx.Timeout(self.timeout, connect=10.0),
                ) as client:
                    with client.stream("POST", url, json=request_body, headers=headers) as resp:
                        if resp.status_code != 200:
                            error_body = resp.read().decode("utf-8", errors="replace")
                            print(f"[ERROR] MiniMax API {resp.status_code}: {error_body[:1000]}")
                            # 打印请求消息摘要
                            for i, msg in enumerate(request_body.get("messages", [])):
                                role = msg.get("role", "")
                                content = msg.get("content", "")
                                tc = msg.get("tool_calls")
                                tcid = msg.get("tool_call_id")
                                print(f"  msg[{i}] role={role} content_len={len(content) if content else 0} tool_calls={bool(tc)} tool_call_id={bool(tcid)}")
                            resp.raise_for_status()
                        for line in resp.iter_lines():
                            if not line.startswith("data: "):
                                continue
                            chunk_str = line[6:].strip()
                            if chunk_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(chunk_str)
                            except json.JSONDecodeError:
                                continue

                            choices = chunk.get("choices", [])
                            if not choices:
                                continue

                            choice = choices[0]
                            delta = choice.get("delta", {})

                            # 处理文本内容
                            content = delta.get("content")
                            if content:
                                result.add_content(content)
                                asyncio.run_coroutine_threadsafe(
                                    queue.put(StreamToolEvent(
                                        event_type=StreamToolEventType.CONTENT,
                                        content=content
                                    )),
                                    loop
                                )

                            # 处理工具调用增量
                            tool_calls = delta.get("tool_calls", [])
                            for tc_delta in tool_calls:
                                idx = tc_delta.get("index", 0)
                                tc_id = tc_delta.get("id", "")
                                tc_func = tc_delta.get("function", {})
                                tc_name = tc_func.get("name", "")
                                tc_args = tc_func.get("arguments", "")

                                # 工具调用开始
                                if tc_id or tc_name:
                                    result.add_tool_call_start(idx, tc_id, tc_name)
                                    asyncio.run_coroutine_threadsafe(
                                        queue.put(StreamToolEvent(
                                            event_type=StreamToolEventType.TOOL_CALL_START,
                                            tool_call_index=idx,
                                            tool_call_id=tc_id,
                                            tool_name=tc_name
                                        )),
                                        loop
                                    )

                                # 工具调用参数增量
                                if tc_args:
                                    result.add_tool_call_delta(idx, tc_args)
                                    asyncio.run_coroutine_threadsafe(
                                        queue.put(StreamToolEvent(
                                            event_type=StreamToolEventType.TOOL_CALL_DELTA,
                                            tool_call_index=idx,
                                            tool_arguments_delta=tc_args
                                        )),
                                        loop
                                    )

                            # 处理结束原因
                            finish_reason = choice.get("finish_reason")
                            if finish_reason:
                                result.finish_reason = finish_reason
                                asyncio.run_coroutine_threadsafe(
                                    queue.put(StreamToolEvent(
                                        event_type=StreamToolEventType.FINISH,
                                        finish_reason=finish_reason
                                    )),
                                    loop
                                )

            except Exception as e:
                asyncio.run_coroutine_threadsafe(queue.put(e), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(_SENTINEL), loop)

        # 在线程池中启动流式调用
        loop.run_in_executor(None, _stream_worker)

        # 从队列中逐个取出事件并 yield
        try:
            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    break
                if isinstance(item, Exception):
                    raise HelloAgentsException(f"流式工具调用失败: {str(item)}")
                yield item
        finally:
            self._last_stream_tool_result = result

    def get_last_stream_tool_result(self) -> Optional[StreamToolCallResult]:
        """
        获取最后一次流式工具调用的累积结果

        Returns:
            StreamToolCallResult 或 None
        """
        return self._last_stream_tool_result
