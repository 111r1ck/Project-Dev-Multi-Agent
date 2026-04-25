from __future__ import annotations

import json
from typing import Any


_CATEGORY_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("capacity", ("qps", "吞吐", "并发", "容量", "峰值", "负载")),
    ("latency", ("响应时间", "延迟", "p95", "p99", "超时")),
    ("availability", ("可用性", "sla", "故障恢复", "停机", "服务等级")),
    ("resilience", ("重试", "降级", "熔断", "故障演练", "异常修复", "队列堆积")),
    ("scalability", ("扩容", "伸缩", "水平扩展", "分片", "多实例")),
    ("consistency", ("幂等", "事务", "补偿", "状态机", "对账", "一致性")),
    ("security_compliance", ("隔离", "权限", "审计", "合规", "风控", "黑名单")),
    ("observability", ("监控", "告警", "日志", "链路追踪", "指标")),
    ("release_safety", ("发布", "灰度", "回滚", "流量切换", "上线", "里程碑")),
    ("data_governance", ("备份", "恢复", "迁移", "归档", "数据保留")),
]


def _compact_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def classify_decision(key: str, value: Any) -> str:
    text = f"{key} {_compact_text(value)}".lower()
    for category, hints in _CATEGORY_HINTS:
        if any(hint.lower() in text for hint in hints):
            return category
    return "confirmed"


def _decision_key(category: str, key: str) -> str:
    normalized = key.strip().lower().replace(" ", "_")
    if category in {
        "capacity",
        "latency",
        "availability",
        "resilience",
        "scalability",
        "consistency",
        "security_compliance",
        "observability",
        "release_safety",
        "data_governance",
    }:
        return category
    return normalized or category


def _empty_decisions() -> dict[str, Any]:
    return {
        "confirmed_constraints": [],
        "scope_decisions": [],
        "technical_decisions": [],
        "delivery_decisions": [],
        "risk_controls": [],
        "superseded_decisions": [],
    }


def merge_project_decisions(
    current: dict[str, Any] | None,
    feedback: dict[str, Any] | str,
    *,
    source_round: int,
) -> dict[str, Any]:
    merged = _empty_decisions()
    if isinstance(current, dict):
        for key in merged:
            value = current.get(key, [])
            merged[key] = list(value) if isinstance(value, list) else []

    if not isinstance(feedback, dict):
        feedback = {"人工补充": feedback}

    active = list(merged["confirmed_constraints"])
    superseded = list(merged["superseded_decisions"])
    by_key = {
        str(item.get("key", "")): idx
        for idx, item in enumerate(active)
        if isinstance(item, dict)
    }
    by_category = {
        str(item.get("category", "")): idx
        for idx, item in enumerate(active)
        if isinstance(item, dict)
    }

    for raw_key, value in feedback.items():
        category = classify_decision(str(raw_key), value)
        key = _decision_key(category, str(raw_key))
        decision = {
            "category": category,
            "key": key,
            "label": str(raw_key),
            "value": value,
            "source_round": source_round,
        }
        if key in by_key or category in by_category:
            old_idx = by_key.get(key, by_category[category])
            old = active[old_idx]
            if isinstance(old, dict):
                superseded.append({**old, "superseded_by_round": source_round})
                decision["key"] = str(old.get("key", key) or key)
            active[old_idx] = decision
        else:
            by_key[key] = len(active)
            by_category[category] = len(active)
            active.append(decision)

    merged["confirmed_constraints"] = active
    merged["superseded_decisions"] = superseded
    return merged
