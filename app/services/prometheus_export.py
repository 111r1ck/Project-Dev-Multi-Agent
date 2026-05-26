from __future__ import annotations

import re
from typing import Any

from app.services.observability import snapshot_metrics


_METRIC_NAME_RE = re.compile(r"[^a-zA-Z0-9_]")


def _sanitize_name(name: str) -> str:
    out = _METRIC_NAME_RE.sub("_", str(name or "").strip())
    if not out:
        out = "metric"
    if out[0].isdigit():
        out = f"m_{out}"
    return out


def _parse_key(key: str) -> tuple[str, dict[str, str]]:
    if "|" not in key:
        return key, {}
    name, labels_raw = key.split("|", 1)
    labels: dict[str, str] = {}
    for pair in (labels_raw.split(",") if labels_raw else []):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        labels[k.strip()] = v.strip()
    return name, labels


def _render_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    parts = [f'{k}="{v}"' for k, v in sorted(labels.items())]
    return "{" + ",".join(parts) + "}"


def render_prometheus_metrics() -> str:
    metrics = snapshot_metrics()
    lines: list[str] = []
    seen_type: set[str] = set()
    for key, value in sorted(metrics.items()):
        raw_name, labels = _parse_key(key)
        name = _sanitize_name(raw_name)
        if name not in seen_type:
            lines.append(f"# TYPE {name} gauge")
            seen_type.add(name)
        lines.append(f"{name}{_render_labels(labels)} {float(value)}")
    if not lines:
        return "\n"
    lines.append("")
    return "\n".join(lines)


def _sum_metric(metrics: dict[str, float], prefix: str, contains: str = "") -> float:
    total = 0.0
    for key, value in metrics.items():
        if not key.startswith(prefix):
            continue
        if contains and contains not in key:
            continue
        total += float(value)
    return total


def evaluate_alerts() -> dict[str, Any]:
    metrics = snapshot_metrics()
    continue_total = _sum_metric(metrics, "workflow_continue_total")
    no_progress_total = _sum_metric(metrics, "workflow_continue_no_progress_total")
    run_total = _sum_metric(metrics, "workflow_run_total")
    run_success = _sum_metric(metrics, "workflow_run_total", "status=success")
    resume_total = _sum_metric(metrics, "workflow_resume_total")
    resume_success = _sum_metric(metrics, "workflow_resume_total", "status=success")

    alerts: list[dict[str, Any]] = []
    if continue_total >= 5:
        ratio = no_progress_total / continue_total if continue_total > 0 else 0.0
        if ratio >= 0.2:
            alerts.append(
                {
                    "name": "continue_no_progress_rate_high",
                    "severity": "warning",
                    "value": round(ratio, 4),
                    "threshold": 0.2,
                    "window_counter": int(continue_total),
                }
            )
    if run_total >= 10:
        success_rate = run_success / run_total if run_total > 0 else 0.0
        if success_rate < 0.8:
            alerts.append(
                {
                    "name": "run_success_rate_low",
                    "severity": "critical",
                    "value": round(success_rate, 4),
                    "threshold": 0.8,
                    "window_counter": int(run_total),
                }
            )
    if resume_total >= 5:
        success_rate = resume_success / resume_total if resume_total > 0 else 0.0
        if success_rate < 0.7:
            alerts.append(
                {
                    "name": "resume_success_rate_low",
                    "severity": "warning",
                    "value": round(success_rate, 4),
                    "threshold": 0.7,
                    "window_counter": int(resume_total),
                }
            )
    return {
        "active": alerts,
        "active_count": len(alerts),
        "counters": {
            "continue_total": continue_total,
            "continue_no_progress_total": no_progress_total,
            "run_total": run_total,
            "run_success": run_success,
            "resume_total": resume_total,
            "resume_success": resume_success,
        },
    }
