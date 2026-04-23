from langchain_core.tools import tool


@tool
def suggest_architecture_style(project_summary: str) -> str:
    """根据需求摘要给出架构风格建议。"""
    if "高并发" in project_summary or "多商户" in project_summary:
        return "模块化单体优先，预留服务拆分边界"
    return "标准前后端分离的模块化单体"
