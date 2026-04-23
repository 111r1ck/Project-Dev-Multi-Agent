# Project Dev Multi-Agent (MVP)

基于 LangChain + LangGraph 的需求驱动开发多 Agent 骨架。

## 快速开始

1. 安装依赖

```bash
pip install -e .[dev]
```

2. 配置环境变量

```bash
cp .env.example .env
```

LLM 提供商切换（默认 `openai`）：

- `LLM_PROVIDER=openai|azure_openai|anthropic|google|ollama|openrouter`
- `LLM_MODEL=...`
- `LLM_TEMPERATURE=0.2`
- `LLM_ENABLE_THINKING=true|false`（留空表示自动；DashScope + Qwen 默认自动关闭，避免 tool_choice 冲突）

示例：

- OpenAI
  - `LLM_PROVIDER=openai`
  - `OPENAI_API_KEY=...`
  - `LLM_MODEL=gpt-5`
- Anthropic
  - `LLM_PROVIDER=anthropic`
  - `ANTHROPIC_API_KEY=...`
  - `LLM_MODEL=claude-3-5-sonnet-latest`
- Google
  - `LLM_PROVIDER=google`
  - `GOOGLE_API_KEY=...`
  - `LLM_MODEL=gemini-2.0-flash`
- Ollama
  - `LLM_PROVIDER=ollama`
  - `OLLAMA_BASE_URL=http://127.0.0.1:11434`
  - `LLM_MODEL=qwen2.5:7b`
- OpenRouter
  - `LLM_PROVIDER=openrouter`
  - `OPENROUTER_API_KEY=...`
  - `LLM_MODEL=openai/gpt-4o-mini`

可选安装多提供商依赖：

```bash
pip install -e .[dev,providers]
```

可选持久化配置：

- `CHECKPOINTER_BACKEND=memory` 使用内存 checkpoint（默认）
- `CHECKPOINTER_BACKEND=sqlite` 使用 SQLite 持久化 checkpoint
- `CHECKPOINTER_BACKEND=postgres` 使用 PostgreSQL 持久化 checkpoint
- `CHECKPOINTER_SQLITE_PATH=.data/checkpoints.sqlite` 指定 SQLite 文件路径
- `CHECKPOINTER_POSTGRES_DSN=postgresql://...` 指定 PostgreSQL 连接串
- `CHECKPOINTER_POSTGRES_PIPELINE=false` 是否启用 pipeline
- `CHECKPOINTER_POSTGRES_AUTO_SETUP=true` 首次启动自动创建 checkpoint 表
- `HUMAN_GATE_MAX_ROUNDS=3` 人工补充最多轮次，达到后自动继续到后续节点

3. 启动服务

```bash
python run_dev.py
```

启动后可打开前端控制台：

- `http://127.0.0.1:8000/`

4. 调用接口

```bash
curl -X POST http://127.0.0.1:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "mall-001",
    "raw_requirement": "开发一个社区电商商城，支持商品浏览、购物车、下单、支付、订单管理。"
  }'
```

5. 人工中断后恢复

```bash
curl -X POST http://127.0.0.1:8000/runs/mall-001/resume \
  -H "Content-Type: application/json" \
  -d '{
    "human_feedback": {
      "补充信息": "先只做微信支付，退款放二期"
    }
  }'
```

6. 查询线程状态

```bash
curl http://127.0.0.1:8000/runs/mall-001/state
```

7. 查询 checkpoint 历史

```bash
curl "http://127.0.0.1:8000/runs/mall-001/history?limit=20"
```

## 项目结构

- `app/agents`: 每个专业 Agent 与 schema
- `app/graph`: LangGraph 状态、节点、路由、图构建
- `app/tools`: Agent 可调用工具
- `app/services`: 纯业务逻辑
- `app/storage`: checkpoint 与存储封装
- `app/api`: FastAPI 路由
- `tests`: 基础测试
