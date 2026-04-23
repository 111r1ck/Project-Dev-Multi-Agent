from langchain_core.tools import tool


@tool
def extract_plain_text_requirement(raw_text: str) -> str:
    """清洗用户输入的原始需求文本。"""
    return raw_text.strip()


@tool
def detect_requirement_gaps(raw_text: str) -> list[str]:
    """粗略识别常见缺失项。"""
    gaps = []
    keywords = {
        "权限": ["角色", "权限"],
        "支付": ["支付", "退款"],
        "部署": ["部署", "服务器", "云"],
        "日志": ["日志", "监控"],
    }
    for name, words in keywords.items():
        if not any(word in raw_text for word in words):
            gaps.append(f"可能缺少{name}相关说明")
    return gaps
