"""
TinyClaw Backend - FastAPI 入口
"""
import os

# 禁用 PYTHONSTARTUP 以避免 I/O 问题
os.environ.pop("PYTHONSTARTUP", None)

from contextlib import asynccontextmanager
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from .api import chat, session, config, memory
from .workspace.manager import WorkspaceManager
from .agent.tinyclaw_agent import TinyClawAgent

# 加载环境变量
load_dotenv()

# 全局 Agent 实例
_agent: TinyClawAgent = None

# API Key 认证配置
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_API_KEY = os.getenv("TINYCLAW_API_KEY")


def get_agent() -> TinyClawAgent:
    """获取全局 Agent 实例"""
    global _agent
    return _agent


async def verify_api_key(
    request: Request,
    api_key: Optional[str] = Depends(_api_key_header),
):
    """API Key 认证依赖

    如果未配置 TINYCLAW_API_KEY 环境变量，则跳过认证（开放模式）。
    否则要求请求携带有效的 API Key（通过 X-API-Key header 或 Authorization: Bearer）。
    """
    if not _API_KEY:
        return  # 未配置 key，跳过认证

    # 支持 X-API-Key header
    if api_key and api_key == _API_KEY:
        return

    # 支持 Authorization: Bearer <key>
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if token == _API_KEY:
            return

    raise HTTPException(
        status_code=401,
        detail="无效或缺失的 API Key。请通过 X-API-Key header 或 Authorization: Bearer 传递。",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global _agent

    # 启动时初始化
    print("TinyClaw Backend starting...")

    if _API_KEY:
        print("API Key authentication: ENABLED")
    else:
        print("API Key authentication: DISABLED (set TINYCLAW_API_KEY to enable)")

    # 初始化工作空间
    workspace_path = os.getenv("WORKSPACE_PATH", "~/.tinyclaw/workspace")
    workspace = WorkspaceManager(workspace_path)
    workspace.ensure_workspace_exists()
    print(f"Workspace initialized at: {workspace.workspace_path}")

    # 设置全局 workspace 实例
    config.set_workspace(workspace)
    memory.set_workspace(workspace)

    # 初始化全局 Agent 实例
    _agent = TinyClawAgent(workspace_path=workspace_path)
    print("TinyClawAgent initialized")

    yield
    # 关闭时清理
    print("TinyClaw Backend shutting down...")


app = FastAPI(
    title="TinyClaw API",
    description="AI Agent powered by HelloAgents",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 健康检查（不需要认证）
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "tinyclaw-backend"}


# 注册 API 路由（需要认证）
app.include_router(chat.router, prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(session.router, prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(config.router, prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(memory.router, prefix="/api", dependencies=[Depends(verify_api_key)])


@app.get("/api")
async def api_root():
    return {"message": "TinyClaw API v0.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True,
    )
