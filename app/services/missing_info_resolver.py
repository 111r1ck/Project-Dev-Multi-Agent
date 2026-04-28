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

_META_CAPABILITY_CLUSTERS: dict[str, tuple[str, ...]] = {
    "compliance_governance": ("合规", "治理", "审计", "监管", "策略", "制度"),
    "security_access": ("认证", "鉴权", "权限", "隔离", "越权", "密钥"),
    "integration_dependency": ("外部依赖", "第三方", "对接", "接口契约", "sla", "回调", "同步"),
    "data_quality_consistency": ("数据质量", "数据一致性", "幂等", "口径", "校验", "清洗"),
    "reliability_resilience": ("可用性", "容错", "降级", "重试", "熔断", "恢复", "容灾"),
    "performance_capacity": ("性能", "延迟", "吞吐", "并发", "容量", "压测", "基准"),
    "observability_auditability": ("监控", "日志", "指标", "链路", "追踪", "告警", "留痕"),
    "lifecycle_operability": ("归档", "保留周期", "备份", "清理", "运维", "发布", "回滚"),
    "financial_accounting": ("成本", "计费", "折旧", "核算", "对账", "预算", "财务准则"),
    "workflow_policy": ("审批", "状态机", "规则引擎", "时效", "优先级", "例外处理"),
}
_RISK_CLUSTER_HIT_BONUS = 0.5

_COMPLEXITY_BASE_THRESHOLDS: dict[str, float] = {
    "low": 6.0,
    "simple": 6.0,
    "s": 6.0,
    "小": 6.0,
    "低": 6.0,
    "medium": 4.0,
    "m": 4.0,
    "中": 4.0,
    "high": 2.0,
    "h": 2.0,
    "large": 2.0,
    "l": 2.0,
    "复杂": 2.0,
    "高": 2.0,
}

_LEVEL_WEIGHTS: dict[str, float] = {
    "must_confirm": 2.0,
    "assumable": 1.0,
    "deferred": 0.5,
}


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


def evaluate_missing_info_signal(
    *,
    missing_info: list[Any],
    complexity: str | None,
    levels: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    normalized_complexity = str(complexity or "").strip().lower()
    base_threshold = _COMPLEXITY_BASE_THRESHOLDS.get(normalized_complexity, 4.0)
    dynamic_threshold = max(2.0, min(8.0, float(base_threshold)))

    resolved_levels = levels or classify_missing_info_levels(missing_info)
    level_weights = dict(_LEVEL_WEIGHTS)

    missing_score = 0.0
    level_counts = {
        "must_confirm": len(resolved_levels.get("must_confirm", []) or []),
        "assumable": len(resolved_levels.get("assumable", []) or []),
        "deferred": len(resolved_levels.get("deferred", []) or []),
    }
    for level_name, items in resolved_levels.items():
        weight = float(level_weights.get(level_name, 0.0))
        missing_score += weight * len(items or [])

    risk_cluster_hits: dict[str, int] = {}
    risk_bonus_hits: list[str] = []
    for item in (missing_info or []):
        text = str(item or "").strip()
        if not text:
            continue
        matched_clusters: list[str] = []
        for cluster_name, hints in _META_CAPABILITY_CLUSTERS.items():
            if _contains_any(text, hints):
                matched_clusters.append(cluster_name)
        if not matched_clusters:
            continue
        # Score by unique cluster hits per item, avoiding repeated word stacking in one cluster.
        unique_clusters = sorted(set(matched_clusters))
        missing_score += _RISK_CLUSTER_HIT_BONUS * len(unique_clusters)
        for cluster_name in unique_clusters:
            risk_cluster_hits[cluster_name] = risk_cluster_hits.get(cluster_name, 0) + 1
        risk_bonus_hits.append(f"{text} -> {','.join(unique_clusters)}")

    return {
        "complexity": normalized_complexity,
        "base_threshold": round(base_threshold, 2),
        "dynamic_threshold": round(dynamic_threshold, 2),
        "missing_score": round(missing_score, 2),
        "must_confirm_count": level_counts["must_confirm"],
        "level_counts": level_counts,
        "risk_cluster_hits": risk_cluster_hits,
        "risk_bonus_hits": risk_bonus_hits,
        "risk_bonus_per_cluster": _RISK_CLUSTER_HIT_BONUS,
        "meta_capability_clusters": sorted(_META_CAPABILITY_CLUSTERS.keys()),
        "level_weights": level_weights,
    }


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
