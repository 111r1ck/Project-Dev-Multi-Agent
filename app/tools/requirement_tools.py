from langchain_core.tools import tool


@tool
def extract_plain_text_requirement(raw_text: str) -> str:
    """清洗用户输入的原始需求文本。"""
    return (raw_text or "").strip()


@tool
def detect_requirement_gaps(raw_text: str) -> list[str]:
    """粗略识别通用需求维度缺失项（领域无关）。"""
    text = (raw_text or "").strip()
    if not text:
        return ["缺少需求描述主体"]

    gaps = []
    dimensions = {
        "目标与范围": ["目标", "范围", "场景", "业务", "用户", "角色", "目标用户"],
        "功能需求": ["功能", "模块", "流程", "接口", "能力", "页面", "任务"],
        "非功能约束": ["性能", "并发", "稳定", "安全", "合规", "可用性", "延迟"],
        "集成与依赖": ["集成", "对接", "第三方", "依赖", "接口文档", "SDK", "外部系统"],
        "验收与里程碑": ["验收", "标准", "里程碑", "阶段", "优先级", "截止", "上线"],
    }
    for name, words in dimensions.items():
        if not any(word in text for word in words):
            gaps.append(f"可能缺少{name}相关说明")
    return gaps
