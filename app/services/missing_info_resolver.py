from __future__ import annotations

from typing import Any


_BLOCKING_HINTS = (
    "身份认证",
    "认证方式",
    "访问控制",
    "权限模型",
    "核心业务规则",
    "核心数据来源",
    "核心外部依赖",
    "强合规",
    "合规红线",
    "法务红线",
    "不可替代",
)
_DEFERRABLE_HINTS = (
    "二期",
    "后续",
    "未来",
    "可选",
    "非核心",
    "增强项",
    "不影响mvp",
    "不影响主链路",
)


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(hint.lower() in normalized for hint in hints)


def build_assumption_pack(
    *,
    missing_info: list[Any],
    requirement_doc: dict[str, Any] | None,
    project_decisions: dict[str, Any] | None,
    human_feedback_notes: list[Any] | None,
) -> dict[str, Any]:
    unresolved = [str(item) for item in (missing_info or []) if str(item).strip()]
    pack = {
        "human_gate_exhausted": True,
        "unresolved_missing_info": unresolved,
        "blocking": [],
        "assumptions": [],
        "risk_controls": [],
        "deferred_scope": [],
        "requires_user_confirmation": [],
    }

    for item in unresolved:
        if _contains_any(item, _BLOCKING_HINTS):
            pack["blocking"].append(item)
            continue

        if _contains_any(item, _DEFERRABLE_HINTS):
            pack["deferred_scope"].append(item)
            pack["requires_user_confirmation"].append(
                {"item": item, "phase": "范围恢复前确认"}
            )
            continue

        assumption = {
            "source": item,
            "assumption": "按保守默认、可替代实现、可降级处理和人工兜底策略继续推进。",
        }
        risk_control = {
            "missing_info": item,
            "control": "提供适配器或mock、超时重试、降级路径、观测指标和上线前复核任务。",
        }
        pack["assumptions"].append(assumption)
        pack["risk_controls"].append(risk_control)
        pack["requires_user_confirmation"].append(
            {"item": item, "phase": "上线前确认"}
        )

    return pack
