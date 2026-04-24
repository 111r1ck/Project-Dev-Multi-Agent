from langchain_core.tools import tool


@tool
def estimate_task_size(task_title: str) -> str:
    """给任务一个非常粗略的规模估算（领域无关）。"""
    title = (task_title or "").strip()
    if not title:
        return "M"

    complexity_markers = [
        "设计",
        "架构",
        "重构",
        "迁移",
        "集成",
        "编排",
        "自动化",
        "安全",
        "治理",
        "引擎",
    ]
    simple_markers = ["文案", "样式", "文档", "修复", "配置", "校验", "列表", "详情"]

    # Long titles with multiple sub-goals are usually larger.
    if len(title) >= 18 and any(sep in title for sep in ["与", "并", "并且", "及", "/"]):
        return "L"
    if any(word in title for word in complexity_markers):
        return "L"
    if len(title) <= 8 or any(word in title for word in simple_markers):
        return "S"
    return "M"
