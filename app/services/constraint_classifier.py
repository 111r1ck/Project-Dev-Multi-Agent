from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConstraintSignal:
    category: str
    evidence: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


_CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "availability": ("可用性", "sla", "服务等级", "故障恢复", "故障切换", "停机", "恢复目标"),
    "capacity": ("容量", "吞吐", "并发", "峰值", "负载", "qps", "tps", "请求量"),
    "latency": ("响应时间", "延迟", "p95", "p99", "超时", "耗时"),
    "resilience": ("限流", "降级", "熔断", "重试", "补偿", "故障演练", "异常修复", "队列堆积"),
    "scalability": ("扩容", "伸缩", "水平扩展", "分片", "多实例", "弹性"),
    "consistency": ("幂等", "事务", "一致性", "状态机", "对账", "补偿", "重复提交"),
    "security_compliance": ("权限", "隔离", "审计", "合规", "风控", "加密", "黑名单"),
    "observability": ("监控", "告警", "日志", "指标", "链路追踪", "追踪", "可观测"),
    "release_safety": ("灰度", "回滚", "发布", "流量切换", "上线", "变更"),
    "data_governance": ("备份", "恢复", "迁移", "归档", "数据保留", "数据治理", "数据模型", "持久化", "schema", "json", "导入", "导出"),
}


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _add_evidence(
    bucket: dict[str, ConstraintSignal],
    category: str,
    evidence: str,
    source: str,
) -> None:
    signal = bucket.setdefault(category, ConstraintSignal(category=category))
    if evidence and evidence not in signal.evidence:
        signal.evidence.append(evidence)
    if source not in signal.sources:
        signal.sources.append(source)


def _scan_text(bucket: dict[str, ConstraintSignal], text: str, source: str) -> None:
    normalized = text.lower()
    for category, hints in _CATEGORY_HINTS.items():
        if any(hint.lower() in normalized for hint in hints):
            _add_evidence(bucket, category, text, source)


def classify_constraints(
    *,
    requirement_doc: dict[str, Any] | None,
    architecture_plan: dict[str, Any] | None,
    project_decisions: dict[str, Any] | None,
    review_report: dict[str, Any] | None,
) -> list[ConstraintSignal]:
    bucket: dict[str, ConstraintSignal] = {}

    req = requirement_doc or {}
    for source_key in ("summary", "modules", "constraints", "uncertainties"):
        value = req.get(source_key)
        if isinstance(value, list):
            for item in value:
                _scan_text(bucket, _flatten_text(item), "requirement_doc")
        else:
            _scan_text(bucket, _flatten_text(value), "requirement_doc")

    arch = architecture_plan or {}
    _scan_text(bucket, _flatten_text(arch), "architecture_plan")

    decisions = project_decisions or {}
    for item in decisions.get("confirmed_constraints", []) or []:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "") or "")
        evidence = _flatten_text(item.get("value", item))
        if category in _CATEGORY_HINTS:
            _add_evidence(bucket, category, evidence, "project_decisions")
        else:
            _scan_text(bucket, evidence, "project_decisions")

    report = review_report or {}
    for key in ("issues", "suggestions"):
        for item in report.get(key, []) or []:
            _scan_text(bucket, _flatten_text(item), "review_report")

    return list(bucket.values())
