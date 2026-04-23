from langchain_core.tools import tool


@tool
def prompt_quality_check(coding_prompt: str) -> bool:
    """检查编码提示词是否具备最小可执行信息。"""
    required_tokens = ["目标", "输入", "输出"]
    return all(token in coding_prompt for token in required_tokens)
