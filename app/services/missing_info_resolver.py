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


def classify_missing_info_levels(missing_info: list[Any]) -> dict[str, list[str]]:
    unresolved = [str(item) for item in (missing_info or []) if str(item).strip()]
    levels = {
        "must_confirm": [],
        "assumable": [],
        "deferred": [],
    }
    for item in unresolved:
        if _contains_any(item, _BLOCKING_HINTS):
            levels["must_confirm"].append(item)
            continue
        if _contains_any(item, _DEFERRABLE_HINTS):
            levels["deferred"].append(item)
            continue
        levels["assumable"].append(item)
    return levels


def build_assumption_pack(
    *,
    missing_info: list[Any],
    requirement_doc: dict[str, Any] | None,
    project_decisions: dict[str, Any] | None,
    human_feedback_notes: list[Any] | None,
) -> dict[str, Any]:
    unresolved = [str(item) for item in (missing_info or []) if str(item).strip()]
    levels = classify_missing_info_levels(unresolved)
    pack = {
        "human_gate_exhausted": True,
        "unresolved_missing_info": unresolved,
        "missing_info_levels": levels,
        "blocking": [],
        "scope_reductions": [],
        "assumptions": [],
        "risk_controls": [],
        "deferred_scope": [],
        "requires_user_confirmation": [],
        "coverage_map": [],
        "prelaunch_checklist": [],
        "conditional_pass_ready": False,
    }

    for item in unresolved:
        if _contains_any(item, _BLOCKING_HINTS):
            pack["blocking"].append(item)
            pack["scope_reductions"].append(
                {
                    "missing_info": item,
                    "action": "将受影响能力收缩为替代方案、mock验证或人工兜底路径，并在范围恢复前完成真实信息确认。",
                }
            )
            pack["risk_controls"].append(
                {
                    "missing_info": item,
                    "control": "明确不可自动假设的边界，提供替代方案验证、人工签核和上线前复核任务。",
                }
            )
            pack["requires_user_confirmation"].append(
                {"item": item, "phase": "架构评审前确认"}
            )
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

    coverage_map = []
    for item in unresolved:
        coverage_map.append(
            {
                "missing_info": item,
                "has_assumption": any(a.get("source") == item for a in pack["assumptions"]),
                "has_risk_control": any(r.get("missing_info") == item for r in pack["risk_controls"]),
                "needs_user_confirmation": any(c.get("item") == item for c in pack["requires_user_confirmation"]),
                "is_blocking": item in pack["blocking"],
            }
        )
    pack["coverage_map"] = coverage_map
    pack["prelaunch_checklist"] = [
        {
            "item": c.get("item", ""),
            "phase": c.get("phase", "上线前确认"),
            "status": "pending",
        }
        for c in pack["requires_user_confirmation"]
    ]
    pack["conditional_pass_ready"] = (
        not bool(pack["blocking"])
        and bool(pack["risk_controls"] or pack["assumptions"])
        and bool(pack["requires_user_confirmation"])
    )

    return pack
