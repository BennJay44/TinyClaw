"""聊天 API 路由"""
import asyncio
import json
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/chat", tags=["chat"])

# SSE 心跳间隔（秒）
SSE_HEARTBEAT_INTERVAL = 15

# 队列哨兵值：表示事件流结束
_SENTINEL = object()


class ChatRequest(BaseModel):
    """聊天请求"""
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """聊天响应"""
    content: str
    session_id: Optional[str] = None


def get_agent():
    """获取全局 Agent 实例"""
    from ..main import get_agent as _get_agent
    return _get_agent()


@router.post("/send/sync", response_model=ChatResponse)
async def send_message_sync(request: ChatRequest):
    """发送消息并获取同步响应"""
    agent = get_agent()
    if not agent:
        return ChatResponse(content="Agent not initialized", session_id=request.session_id)

    response = agent.chat(request.message, request.session_id)
    return ChatResponse(content=response, session_id=request.session_id)


@router.post("/send/stream")
async def send_message_stream(request: ChatRequest):
    """发送消息并获取流式响应 (SSE)

    事件类型：
    - session: 会话信息（包含 session_id）
    - step_start: 步骤开始
    - chunk: LLM 文本块
    - tool_start: 工具调用开始
    - tool_finish: 工具调用结束
    - step_finish: 步骤结束
    - done: 完成
    - error: 错误
    - ping: 心跳（保持连接）
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def heartbeat():
        """定期发送心跳保持连接"""
        try:
            while True:
                await asyncio.sleep(SSE_HEARTBEAT_INTERVAL)
                await queue.put({"event": "ping", "data": ""})
        except asyncio.CancelledError:
            pass

    async def produce_events():
        """生产事件并放入队列"""
        agent = get_agent()
        if not agent:
            await queue.put({
                "event": "error",
                "data": json.dumps({"error": "Agent not initialized"}, ensure_ascii=False)
            })
            await queue.put(_SENTINEL)
            return

        try:
            async for event in agent.achat(request.message, request.session_id):
                event_type = event.type.value
                event_data = event.data

                if event_type == "agent_start":
                    session_id = getattr(agent, '_current_session_id', None)
                    await queue.put({
                        "event": "session",
                        "data": json.dumps({"session_id": session_id}, ensure_ascii=False)
                    })
                elif event_type == "step_start":
                    await queue.put({
                        "event": "step_start",
                        "data": json.dumps({
                            "step": event_data.get("step", 1),
                            "max_steps": event_data.get("max_steps", 10)
                        }, ensure_ascii=False)
                    })
                elif event_type == "llm_chunk":
                    chunk = event_data.get("chunk", "")
                    await queue.put({
                        "event": "chunk",
                        "data": json.dumps({"content": chunk}, ensure_ascii=False)
                    })
                elif event_type == "tool_call_start":
                    await queue.put({
                        "event": "tool_start",
                        "data": json.dumps({
                            "tool": event_data.get("tool_name", ""),
                            "args": event_data.get("args", {})
                        }, ensure_ascii=False)
                    })
                elif event_type == "tool_call_finish":
                    await queue.put({
                        "event": "tool_finish",
                        "data": json.dumps({
                            "tool": event_data.get("tool_name", ""),
                            "result": event_data.get("result", "")
                        }, ensure_ascii=False)
                    })
                elif event_type == "step_finish":
                    await queue.put({
                        "event": "step_finish",
                        "data": json.dumps({
                            "step": event_data.get("step", 1)
                        }, ensure_ascii=False)
                    })
                elif event_type == "agent_finish":
                    session_id = agent.save_current_session()
                    final_content = event_data.get("result", "")
                    await queue.put({
                        "event": "done",
                        "data": json.dumps({
                            "content": final_content,
                            "session_id": session_id
                        }, ensure_ascii=False)
                    })
                elif event_type == "error":
                    await queue.put({
                        "event": "error",
                        "data": json.dumps({"error": event_data.get("error", "Unknown error")}, ensure_ascii=False)
                    })

        except Exception as e:
            import traceback
            traceback.print_exc()
            await queue.put({
                "event": "error",
                "data": json.dumps({"error": str(e)}, ensure_ascii=False)
            })
        finally:
            await queue.put(_SENTINEL)

    async def event_generator():
        """SSE 事件生成器：从队列消费事件"""
        heartbeat_task = asyncio.create_task(heartbeat())
        producer_task = asyncio.create_task(produce_events())

        try:
            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    break
                yield item
        finally:
            heartbeat_task.cancel()
            producer_task.cancel()

    return EventSourceResponse(event_generator())


@router.post("/send")
async def send_message(request: ChatRequest):
    """发送消息（暂返回同步响应）"""
    return await send_message_sync(request)
