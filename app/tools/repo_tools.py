from langchain_core.tools import tool


@tool
def suggest_repo_bootstrap(project_name: str) -> list[str]:
    """根据项目名给出仓库初始化建议。"""
    return [
        f"创建仓库: {project_name}",
        "初始化 CI、测试与格式化配置",
        "建立 docs、src、tests 目录骨架",
    ]
