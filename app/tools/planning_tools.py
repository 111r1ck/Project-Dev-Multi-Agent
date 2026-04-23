from langchain_core.tools import tool


@tool
def estimate_task_size(task_title: str) -> str:
    """给任务一个非常粗略的规模估算。"""
    if "支付" in task_title or "权限" in task_title:
        return "L"
    if "列表" in task_title or "详情" in task_title:
        return "S"
    return "M"
