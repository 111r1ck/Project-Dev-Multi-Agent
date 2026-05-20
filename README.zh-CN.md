# Project Dev Multi-Agent (MVP)

[English](./README.md)

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
- 可选按 agent 覆盖模型：
  - `REQUIREMENT_LLM_MODEL=...`
  - `FEASIBILITY_LLM_MODEL=...`
  - `ARCHITECT_LLM_MODEL=...`
  - `PLANNER_LLM_MODEL=...`
  - `PROMPT_BUILDER_LLM_MODEL=...`
  - `REVIEWER_LLM_MODEL=...`
  - 若不设置则回退到全局 `LLM_MODEL`

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
- `RATE_LIMIT_ENABLED=false` 是否启用 Redis 限流
- `REDIS_URL=redis://127.0.0.1:6379/0` Redis 地址
- `RATE_LIMIT_WINDOW_SECONDS=60` 限流窗口（秒）
- `RATE_LIMIT_RUNS_PER_WINDOW=60` `/runs` 系列接口每窗口允许请求数
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

## Codex MCP 接入（导出工具）

如需让 Codex 通过 MCP 直接调用本项目导出能力：

1. 安装 MCP 依赖

```bash
pip install -e .[mcp]
```

2. 启动 MCP server（stdio）

```bash
codex-export-mcp
```

3. 可用工具（11个）

- `list_export_capabilities`
- `get_run_state_summary(project_id)`
- `get_run_section(project_id, section)`
- `preview_run_export_content(project_id, export_format, sections)`
- `export_run_artifact_tool(project_id, export_format, sections)`
- `export_run_sections_bundle(project_id, export_format, sections)`
- `list_project_exports(project_id, limit)`
- `read_project_export_file(project_id, filename)`
- `start_new_run(raw_requirement, project_id, project_prefix)`
- `continue_run(project_id)`
- `resume_run_with_feedback(project_id, human_feedback)`

说明：

- 该 MCP server 复用现有导出服务，文件写入 `exports/{project_id}/`。
- 保持与 HTTP 导出接口并行，不破坏现有前端与 API 调用链路。

## 项目结构

- `app/agents`: 每个专业 Agent 与 schema
- `app/graph`: LangGraph 状态、节点、路由、图构建
- `app/tools`: Agent 可调用工具
- `app/services`: 纯业务逻辑
- `app/storage`: checkpoint 与存储封装
- `app/api`: FastAPI 路由
- `tests`: 基础测试

## 发布到 GitHub 前检查清单

1. 确认未提交敏感信息

- `.env` 已在 `.gitignore` 中，不应被跟踪
- 仅提交 `.env.example` 作为模板

2. 运行测试

```bash
pytest
```

3. 检查当前改动

```bash
git status
```

4. 提交并推送

```bash
git add .
git commit -m "chore: prepare repository for GitHub publishing"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

说明：

- 本仓库已提供 `LICENSE`（MIT）与 GitHub Actions CI（`.github/workflows/ci.yml`）。
- CI 会在 `main/master` 的 push 和 pull request 上自动运行 `pytest`。
