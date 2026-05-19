from __future__ import annotations

import csv
import hashlib
import json
from io import StringIO
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPPORTED_EXPORT_FORMATS = {"json", "md", "csv"}
SUPPORTED_EXPORT_SECTIONS = {
    "summary",
    "requirement_doc",
    "feasibility_report",
    "architecture_plan",
    "tasks",
    "prompts",
    "review",
    "diagnostics",
}


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_project_id(project_id: str) -> str:
    cleaned = "".join(ch for ch in str(project_id or "unknown") if ch.isalnum() or ch in ("-", "_"))
    return cleaned or "unknown"


def _build_payload(values: dict[str, Any], sections: list[str]) -> dict[str, Any]:
    report = values.get("review_report", {}) or {}
    diagnostics = report.get("diagnostics", [])
    payload: dict[str, Any] = {}
    for section in sections:
        if section == "summary":
            payload["summary"] = {
                "project_id": values.get("project_id", ""),
                "status": "completed" if bool(report) else "in_progress",
                "review_passed": bool(report.get("passed")) if isinstance(report, dict) else None,
                "task_count": len(values.get("task_breakdown", []) or []),
                "prompt_count": len(values.get("prompt_pack", []) or []),
                "review_issue_count": len(report.get("issues", []) or []) if isinstance(report, dict) else 0,
                "review_suggestion_count": len(report.get("suggestions", []) or []) if isinstance(report, dict) else 0,
                "review_diagnostics_count": len(diagnostics) if isinstance(diagnostics, list) else 0,
            }
        elif section == "requirement_doc":
            payload["requirement_doc"] = values.get("requirement_doc", {}) or {}
        elif section == "feasibility_report":
            payload["feasibility_report"] = values.get("feasibility_report", {}) or {}
        elif section == "architecture_plan":
            payload["architecture_plan"] = values.get("architecture_plan", {}) or {}
        elif section == "tasks":
            payload["tasks"] = values.get("task_breakdown", []) or []
        elif section == "prompts":
            payload["prompts"] = values.get("prompt_pack", []) or []
        elif section == "review":
            payload["review"] = values.get("review_report", {}) or {}
        elif section == "diagnostics":
            payload["diagnostics"] = diagnostics if isinstance(diagnostics, list) else []
    return payload


def _render_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _render_markdown_bytes(payload: dict[str, Any]) -> bytes:
    lines: list[str] = ["# Run Export", ""]
    summary = payload.get("summary", {})
    if isinstance(summary, dict) and summary:
        lines.append("## Summary")
        for key, value in summary.items():
            lines.append(f"- **{key}**: {value}")
        lines.append("")
    requirement_doc = payload.get("requirement_doc", {})
    if isinstance(requirement_doc, dict) and requirement_doc:
        lines.append("## Requirement Doc")
        lines.append("```json")
        lines.append(json.dumps(requirement_doc, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    feasibility_report = payload.get("feasibility_report", {})
    if isinstance(feasibility_report, dict) and feasibility_report:
        lines.append("## Feasibility Report")
        lines.append("```json")
        lines.append(json.dumps(feasibility_report, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    architecture_plan = payload.get("architecture_plan", {})
    if isinstance(architecture_plan, dict) and architecture_plan:
        lines.append("## Architecture Plan")
        lines.append("```json")
        lines.append(json.dumps(architecture_plan, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    tasks = payload.get("tasks", [])
    if isinstance(tasks, list) and tasks:
        lines.append("## Tasks")
        for item in tasks:
            title = str((item or {}).get("title", "")).strip()
            priority = str((item or {}).get("priority", "")).strip()
            deps = (item or {}).get("depends_on", []) or []
            lines.append(f"- `{title}` ({priority}) deps={len(deps)}")
        lines.append("")
    review = payload.get("review", {})
    if isinstance(review, dict) and review:
        lines.append("## Review")
        lines.append(f"- passed: {bool(review.get('passed'))}")
        issues = review.get("issues", []) or []
        suggestions = review.get("suggestions", []) or []
        lines.append(f"- issues: {len(issues)}")
        lines.append(f"- suggestions: {len(suggestions)}")
        if issues:
            lines.append("- issue details:")
            for issue in issues:
                lines.append(f"  - {issue}")
        if suggestions:
            lines.append("- suggestion details:")
            for suggestion in suggestions:
                lines.append(f"  - {suggestion}")
        lines.append("")
    diagnostics = payload.get("diagnostics", [])
    if isinstance(diagnostics, list) and diagnostics:
        lines.append("## Diagnostics")
        lines.append(f"- count: {len(diagnostics)}")
        lines.append("")
    return "\n".join(lines).encode("utf-8")


def _render_csv_bytes(payload: dict[str, Any]) -> bytes:
    rows: list[dict[str, Any]] = []
    tasks = payload.get("tasks", [])
    if isinstance(tasks, list) and tasks:
        for task in tasks:
            rows.append(
                {
                    "kind": "task",
                    "title": str((task or {}).get("title", "")),
                    "priority": str((task or {}).get("priority", "")),
                    "owner_role": str((task or {}).get("owner_role", "")),
                    "depends_on_count": len((task or {}).get("depends_on", []) or []),
                }
            )
    diagnostics = payload.get("diagnostics", [])
    if isinstance(diagnostics, list) and diagnostics:
        for item in diagnostics:
            rows.append(
                {
                    "kind": "diagnostic",
                    "title": str((item or {}).get("issue_text", "")),
                    "priority": "",
                    "owner_role": "",
                    "depends_on_count": "",
                }
            )
    if not rows:
        rows.append({"kind": "summary", "title": "empty", "priority": "", "owner_role": "", "depends_on_count": ""})

    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["kind", "title", "priority", "owner_role", "depends_on_count"],
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_bytes(_render_json_bytes(payload))


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    path.write_bytes(_render_markdown_bytes(payload))


def _write_csv(path: Path, payload: dict[str, Any]) -> None:
    path.write_bytes(_render_csv_bytes(payload))


def build_run_export_content(
    *,
    project_id: str,
    values: dict[str, Any],
    export_format: str,
    sections: list[str],
) -> dict[str, Any]:
    fmt = str(export_format or "").strip().lower()
    if fmt not in SUPPORTED_EXPORT_FORMATS:
        raise ValueError(f"unsupported format: {export_format}")
    if not sections:
        raise ValueError("sections must not be empty")
    if any(section not in SUPPORTED_EXPORT_SECTIONS for section in sections):
        raise ValueError("unsupported section in sections")

    payload = _build_payload(values, sections)
    safe_id = _safe_project_id(project_id)
    unique_sections = [s for s in sections if s]
    if len(unique_sections) == 1:
        section_tag = unique_sections[0]
    else:
        section_tag = "merged"
    filename = f"run_export_{safe_id}_{section_tag}_{_now_stamp()}.{fmt}"
    if fmt == "json":
        raw = _render_json_bytes(payload)
        mime = "application/json"
    elif fmt == "md":
        raw = _render_markdown_bytes(payload)
        mime = "text/markdown"
    else:
        raw = _render_csv_bytes(payload)
        mime = "text/csv"
    return {
        "filename": filename,
        "mime_type": mime,
        "bytes": raw,
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def export_run_artifact(
    *,
    project_id: str,
    values: dict[str, Any],
    export_format: str,
    sections: list[str],
    base_dir: str = "exports",
) -> dict[str, Any]:
    fmt = str(export_format or "").strip().lower()
    if fmt not in SUPPORTED_EXPORT_FORMATS:
        raise ValueError(f"unsupported format: {export_format}")
    if not sections:
        raise ValueError("sections must not be empty")
    if any(section not in SUPPORTED_EXPORT_SECTIONS for section in sections):
        raise ValueError("unsupported section in sections")
    content = build_run_export_content(
        project_id=project_id,
        values=values,
        export_format=fmt,
        sections=sections,
    )
    safe_id = _safe_project_id(project_id)
    out_dir = Path(base_dir) / safe_id
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = str(content["filename"])
    out_path = out_dir / filename
    out_path.write_bytes(content["bytes"])
    return {
        "project_id": project_id,
        "format": fmt,
        "sections": sections,
        "file_path": str(out_path.resolve()),
        "mime_type": str(content["mime_type"]),
        "size_bytes": int(content["size_bytes"]),
        "sha256": str(content["sha256"]),
    }
