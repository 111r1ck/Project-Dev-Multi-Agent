# Project Dev Multi-Agent (MVP)

[中文文档](./README.zh-CN.md)

Requirement-driven multi-agent development scaffold built with LangChain + LangGraph.

## Quick Start

1. Install dependencies

```bash
pip install -e .[dev]
```

2. Configure environment variables

```bash
cp .env.example .env
```

3. Start service

```bash
python run_dev.py
```

4. Open web console

- `http://127.0.0.1:8000/`

## LLM Provider Switching

- `LLM_PROVIDER=openai|azure_openai|anthropic|google|ollama|openrouter`
- `LLM_MODEL=...`
- `LLM_TEMPERATURE=0.2`
- Optional per-agent model overrides:
  - `REQUIREMENT_LLM_MODEL`
  - `FEASIBILITY_LLM_MODEL`
  - `ARCHITECT_LLM_MODEL`
  - `PLANNER_LLM_MODEL`
  - `PROMPT_BUILDER_LLM_MODEL`
  - `REVIEWER_LLM_MODEL`

Optional extra providers:

```bash
pip install -e .[dev,providers]
```

## MCP Integration (Export Tools)

1. Install MCP dependencies

```bash
pip install -e .[mcp]
```

2. Start MCP server (stdio)

```bash
codex-export-mcp
```

3. Available MCP tools (11)

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

## Repository Layout

- `app/agents`: specialized agents and schemas
- `app/graph`: graph state, nodes, routes, builder
- `app/tools`: callable tools for agents
- `app/services`: business logic
- `app/storage`: checkpoint and persistence wrappers
- `app/api`: FastAPI routes
- `tests`: test suite

## GitHub Publishing Checklist

1. Ensure no secrets are tracked (`.env` must remain ignored)
2. Run tests:

```bash
pytest
```

3. Check changes:

```bash
git status
```

4. Commit and push:

```bash
git add .
git commit -m "chore: prepare repository for GitHub publishing"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```
