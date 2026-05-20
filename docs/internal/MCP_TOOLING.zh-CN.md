# MCP 最小发布标准

[English](./MCP_TOOLING.md)

## 范围

当前 MCP 服务（`codex-export-mcp`）覆盖：

- 运行生命周期：`start_new_run`、`continue_run`、`resume_run_with_feedback`
- 状态读取：`get_run_state_summary`、`get_run_section`
- 导出能力：预览/导出/列出/读取

## 安全边界

- 使用 `stdio` 传输，仅适用于本地可信运行环境。
- 服务进程内无内建鉴权。
- 不要将 MCP 进程直接暴露给不可信网络客户端。
- 导出文件读取已拒绝路径分隔符输入。

## 错误语义

- `ValueError`：参数非法、格式不支持、分段不支持。
- `FileNotFoundError`：导出文件不存在。
- 项目状态为空时：
  - summary 接口返回 `status=not_found`
  - section/export 接口可能抛出 `ValueError`

## 兼容性

- 首选导入：`mcp.server.fastmcp.FastMCP`
- 兜底导入：`fastmcp.FastMCP`
- 入口脚本：`codex-export-mcp`

## 最低测试门槛

1. 工具函数单测通过。
2. 生命周期集成测试（mock graph）通过。
3. 现有 API/Web 回归测试通过。

## 发布前检查清单

1. 在发布环境跑全量测试。
2. 验证 `codex-export-mcp` 可正常启动。
3. 验证一条端到端流程：启动 -> 继续/恢复 -> 预览 -> 导出。
4. 确认 `exports/` 已加入 `.gitignore`。
5. 保持 README 的 MCP 说明与实际工具一致。

## 发布定位

在补齐更广泛的鲁棒性与并发测试前，建议以 **Beta / Experimental（实验版）** 对外发布。
