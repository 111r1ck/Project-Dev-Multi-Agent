# MCP Tooling Minimum Release Standard

[中文文档](./MCP_TOOLING.zh-CN.md)

## Scope

Current MCP server (`codex-export-mcp`) covers:

- Run lifecycle: `start_new_run`, `continue_run`, `resume_run_with_feedback`
- State reads: `get_run_state_summary`, `get_run_section`
- Export operations: preview/export/list/read

## Security Boundary

- `stdio` transport only, intended for local trusted runtime.
- No built-in auth in server process.
- Do not expose MCP process to untrusted network clients.
- Export file reading rejects path separators.

## Error Semantics

- `ValueError`: invalid input / unsupported format / unsupported section.
- `FileNotFoundError`: exported file not found.
- Empty state:
  - summary returns `status=not_found`
  - section/export calls may raise `ValueError`

## Compatibility

- Preferred import: `mcp.server.fastmcp.FastMCP`
- Fallback import: `fastmcp.FastMCP`
- Entry script: `codex-export-mcp`

## Minimum Test Bar

1. Unit helper tests are green.
2. Lifecycle integration tests (mock graph) are green.
3. Existing API/web regression tests are green.

## Pre-release Checklist

1. Run full test suite in release environment.
2. Verify `codex-export-mcp` starts correctly.
3. Validate one end-to-end flow: start -> continue/resume -> preview -> export.
4. Confirm `exports/` is git-ignored.
5. Keep README MCP section aligned with actual tools.

## Release Positioning

Until broader resilience and concurrency tests are added, publish as **Beta / Experimental**.
