from __future__ import annotations

import inspect
import json
import secrets
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.dependencies import get_compiled_graph
from app.services.report_renderer import render_result
from app.services.export_service import (
    SUPPORTED_EXPORT_FORMATS,
    SUPPORTED_EXPORT_SECTIONS,
    build_run_export_content,
    export_run_artifact,
)
from langgraph.types import Command

try:
    from mcp.server.fastmcp import FastMCP
except Exception as exc:  # pragma: no cover
    try:
        from fastmcp import FastMCP
    except Exception as fallback_exc:  # pragma: no cover
        FastMCP = None  # type: ignore[assignment]
        _IMPORT_ERROR = fallback_exc
    else:
        _IMPORT_ERROR = None
else:
    _IMPORT_ERROR = None


def _serialize_state_values(project_id: str) -> dict[str, Any]:
    graph = get_compiled_graph()
    snapshot = graph.get_state({"configurable": {"thread_id": project_id}})
    values = _to_jsonable(getattr(snapshot, "values", {}) or {})
    return values if isinstance(values, dict) else {}


def _generate_project_id(prefix: str = "run") -> str:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    token = secrets.token_hex(3)
    cleaned = "".join(ch for ch in str(prefix or "run") if ch.isalnum() or ch in ("-", "_")) or "run"
    return f"{cleaned}-{ts}-{token}"


def _to_jsonable(value: Any) -> Any:
    """Serialize arbitrary objects into JSON-safe primitives without FastAPI."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v) for v in value]
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if hasattr(value, "model_dump"):
        try:
            return _to_jsonable(value.model_dump())
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            return _to_jsonable(value.dict())
        except Exception:
            pass
    try:
        json.dumps(value)
        return value
    except Exception:
        return str(value)


def _normalize_sections(sections: list[str] | None) -> list[str]:
    if not sections:
        return sorted(SUPPORTED_EXPORT_SECTIONS)
    normalized = [str(item or "").strip().lower() for item in sections if str(item or "").strip()]
    if not normalized:
        return sorted(SUPPORTED_EXPORT_SECTIONS)
    invalid = [item for item in normalized if item not in SUPPORTED_EXPORT_SECTIONS]
    if invalid:
        raise ValueError(f"unsupported sections: {invalid}; supported={sorted(SUPPORTED_EXPORT_SECTIONS)}")
    return normalized


def _build_state_summary(values: dict[str, Any]) -> dict[str, Any]:
    review = values.get("review_report", {}) or {}
    diagnostics = review.get("diagnostics", []) if isinstance(review, dict) else []
    return {
        "project_id": values.get("project_id"),
        "task_count": len(values.get("task_breakdown", []) or []),
        "prompt_count": len(values.get("prompt_pack", []) or []),
        "review_passed": bool(review.get("passed")) if isinstance(review, dict) else None,
        "issue_count": len(review.get("issues", []) or []) if isinstance(review, dict) else 0,
        "suggestion_count": len(review.get("suggestions", []) or []) if isinstance(review, dict) else 0,
        "diagnostics_count": len(diagnostics) if isinstance(diagnostics, list) else 0,
        "available_sections": sorted(SUPPORTED_EXPORT_SECTIONS),
    }


def _section_value(values: dict[str, Any], section: str) -> Any:
    sec = str(section or "").strip().lower()
    if sec == "summary":
        return _build_state_summary(values)
    if sec == "requirement_doc":
        return values.get("requirement_doc", {}) or {}
    if sec == "feasibility_report":
        return values.get("feasibility_report", {}) or {}
    if sec == "architecture_plan":
        return values.get("architecture_plan", {}) or {}
    if sec == "tasks":
        return values.get("task_breakdown", []) or []
    if sec == "prompts":
        return values.get("prompt_pack", []) or []
    if sec == "review":
        return values.get("review_report", {}) or {}
    if sec == "diagnostics":
        review = values.get("review_report", {}) or {}
        diagnostics = review.get("diagnostics", []) if isinstance(review, dict) else []
        return diagnostics if isinstance(diagnostics, list) else []
    raise ValueError(f"unsupported section: {section}")


def _list_project_export_files(project_id: str, base_dir: str = "exports") -> list[dict[str, Any]]:
    safe_id = "".join(ch for ch in str(project_id or "") if ch.isalnum() or ch in ("-", "_"))
    if not safe_id:
        return []
    folder = Path(base_dir) / safe_id
    if not folder.exists() or not folder.is_dir():
        return []
    files: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        stat = path.stat()
        files.append(
            {
                "name": path.name,
                "path": str(path.resolve()),
                "size_bytes": int(stat.st_size),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        )
    return files


def _safe_project_folder(project_id: str, base_dir: str = "exports") -> Path:
    safe_id = "".join(ch for ch in str(project_id or "") if ch.isalnum() or ch in ("-", "_"))
    if not safe_id:
        raise ValueError("invalid project_id")
    return Path(base_dir) / safe_id


def _read_export_file(project_id: str, filename: str, base_dir: str = "exports") -> dict[str, Any]:
    name = str(filename or "").strip()
    if not name or "/" in name or "\\" in name:
        raise ValueError("invalid filename")
    folder = _safe_project_folder(project_id, base_dir=base_dir)
    path = folder / name
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"export file not found: {name}")
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    return {
        "project_id": project_id,
        "name": name,
        "path": str(path.resolve()),
        "size_bytes": len(raw),
        "content": text,
    }


def _serialize_interrupt(item: Any) -> Any:
    value = getattr(item, "value", None)
    return value if value is not None else str(item)


def _format_run_result(project_id: str, result: dict[str, Any]) -> dict[str, Any]:
    raw_interrupts = result.get("__interrupt__", [])
    interrupts = [_serialize_interrupt(item) for item in (raw_interrupts or [])]
    if interrupts:
        return {
            "project_id": project_id,
            "status": "interrupted",
            "interrupts": interrupts,
            "state": _to_jsonable(result),
        }
    return {
        "project_id": project_id,
        "status": "completed",
        "result": render_result(result),
        "state": _to_jsonable(result),
    }


def _snapshot_pending_interrupts(snapshot: Any) -> list[Any]:
    pending: list[Any] = []
    for task in (getattr(snapshot, "tasks", ()) or ()):
        for item in (getattr(task, "interrupts", ()) or ()):
            pending.append(_serialize_interrupt(item))
    return pending


if FastMCP is not None:
    mcp = FastMCP("multi-agent-export")

    @mcp.tool()
    def list_export_capabilities() -> dict[str, Any]:
        """List export formats and sections supported by this project."""
        return {
            "formats": sorted(SUPPORTED_EXPORT_FORMATS),
            "sections": sorted(SUPPORTED_EXPORT_SECTIONS),
            "mode": "persist_and_preview",
            "tools": [
                "get_run_state_summary",
                "get_run_section",
                "preview_run_export_content",
                "export_run_artifact_tool",
                "export_run_sections_bundle",
                "list_project_exports",
                "read_project_export_file",
                "start_new_run",
                "continue_run",
                "resume_run_with_feedback",
            ],
            "note": "Exports are written under exports/{project_id}/; preview tool returns text without writing.",
        }

    @mcp.tool()
    def get_run_state_summary(project_id: str) -> dict[str, Any]:
        """Get a compact run summary for a project id."""
        values = _serialize_state_values(project_id)
        if not values:
            return {
                "project_id": project_id,
                "status": "not_found",
                "message": "no state values found",
            }
        summary = _build_state_summary(values)
        summary["status"] = "ok"
        return summary

    @mcp.tool()
    def get_run_section(project_id: str, section: str) -> dict[str, Any]:
        """Read one normalized section from the latest state values for a project id."""
        sec = str(section or "").strip().lower()
        if sec not in SUPPORTED_EXPORT_SECTIONS:
            raise ValueError(f"unsupported section: {sec}; supported={sorted(SUPPORTED_EXPORT_SECTIONS)}")
        values = _serialize_state_values(project_id)
        if not values:
            raise ValueError("no state values found for project_id")
        return {
            "project_id": project_id,
            "section": sec,
            "value": _section_value(values, sec),
        }

    @mcp.tool()
    def export_run_artifact_tool(
        project_id: str,
        export_format: str = "json",
        sections: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Export run result to a file and return metadata.
        Files are written to exports/{project_id}/.
        """
        fmt = str(export_format or "").strip().lower()
        if fmt not in SUPPORTED_EXPORT_FORMATS:
            raise ValueError(f"unsupported format: {fmt}; supported={sorted(SUPPORTED_EXPORT_FORMATS)}")
        normalized_sections = _normalize_sections(sections)
        values = _serialize_state_values(project_id)
        if not values:
            raise ValueError("no state values found for project_id")
        return export_run_artifact(
            project_id=project_id,
            values=values,
            export_format=fmt,
            sections=normalized_sections,
        )

    @mcp.tool()
    def export_run_sections_bundle(
        project_id: str,
        export_format: str = "json",
        sections: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Export each selected section into a separate file and return metadata list.
        Files are written to exports/{project_id}/.
        """
        fmt = str(export_format or "").strip().lower()
        if fmt not in SUPPORTED_EXPORT_FORMATS:
            raise ValueError(f"unsupported format: {fmt}; supported={sorted(SUPPORTED_EXPORT_FORMATS)}")
        normalized_sections = _normalize_sections(sections)
        values = _serialize_state_values(project_id)
        if not values:
            raise ValueError("no state values found for project_id")
        files: list[dict[str, Any]] = []
        for sec in normalized_sections:
            files.append(
                export_run_artifact(
                    project_id=project_id,
                    values=values,
                    export_format=fmt,
                    sections=[sec],
                )
            )
        return {
            "project_id": project_id,
            "format": fmt,
            "count": len(files),
            "files": files,
        }

    @mcp.tool()
    def list_project_exports(project_id: str, limit: int = 50) -> dict[str, Any]:
        """List generated export files for a project under exports/{project_id}/."""
        n = max(1, min(int(limit), 200))
        files = _list_project_export_files(project_id)
        return {
            "project_id": project_id,
            "count": len(files),
            "files": files[:n],
        }

    @mcp.tool()
    def preview_run_export_content(
        project_id: str,
        export_format: str = "json",
        sections: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Build export content in memory (no file write), return preview text and metadata.
        """
        fmt = str(export_format or "").strip().lower()
        if fmt not in SUPPORTED_EXPORT_FORMATS:
            raise ValueError(f"unsupported format: {fmt}; supported={sorted(SUPPORTED_EXPORT_FORMATS)}")
        normalized_sections = _normalize_sections(sections)
        values = _serialize_state_values(project_id)
        if not values:
            raise ValueError("no state values found for project_id")
        content = build_run_export_content(
            project_id=project_id,
            values=values,
            export_format=fmt,
            sections=normalized_sections,
        )
        text = bytes(content["bytes"]).decode("utf-8", errors="replace")
        return {
            "project_id": project_id,
            "format": fmt,
            "sections": normalized_sections,
            "filename": str(content["filename"]),
            "mime_type": str(content["mime_type"]),
            "size_bytes": int(content["size_bytes"]),
            "sha256": str(content["sha256"]),
            "content": text,
        }

    @mcp.tool()
    def read_project_export_file(project_id: str, filename: str) -> dict[str, Any]:
        """Read one exported file by name from exports/{project_id}/."""
        return _read_export_file(project_id=project_id, filename=filename)

    @mcp.tool()
    def start_new_run(
        raw_requirement: str,
        project_id: str | None = None,
        project_prefix: str = "run",
    ) -> dict[str, Any]:
        """
        Start a run with a new or provided project_id.
        Returns interrupted/completed status and current state.
        """
        requirement = str(raw_requirement or "").strip()
        if not requirement:
            raise ValueError("raw_requirement must not be empty")
        pid = str(project_id or "").strip() or _generate_project_id(project_prefix)
        compiled_graph = get_compiled_graph()
        config = {"configurable": {"thread_id": pid}}

        preserved_term_cluster_memory: dict[str, Any] = {}
        try:
            snapshot = compiled_graph.get_state(config)
            values = _to_jsonable(getattr(snapshot, "values", {}) or {})
            memory = values.get("term_cluster_memory", {}) if isinstance(values, dict) else {}
            if isinstance(memory, dict):
                preserved_term_cluster_memory = memory
        except Exception:
            preserved_term_cluster_memory = {}

        result = compiled_graph.invoke(
            {
                "project_id": pid,
                "thread_id": pid,
                "raw_requirement": requirement,
                "human_feedback_notes": [],
                "project_decisions": {},
                "assumption_pack": {},
                "errors": [],
                "need_human": False,
                "human_rounds": 0,
                "max_human_rounds": settings.human_gate_max_rounds,
                "review_rounds": 0,
                "max_review_rounds": settings.review_max_rounds,
                "next_step": "requirement_analyst",
                "term_cluster_memory": preserved_term_cluster_memory,
            },
            config,
        )
        return _format_run_result(pid, result)

    @mcp.tool()
    def continue_run(project_id: str) -> dict[str, Any]:
        """
        Continue a paused/in-progress run synchronously.
        """
        pid = str(project_id or "").strip()
        if not pid:
            raise ValueError("project_id must not be empty")
        compiled_graph = get_compiled_graph()
        config = {"configurable": {"thread_id": pid}}
        snapshot = compiled_graph.get_state(config)
        next_nodes = list(getattr(snapshot, "next", ()) or ())
        pending_interrupts = _snapshot_pending_interrupts(snapshot)
        if pending_interrupts:
            return {
                "project_id": pid,
                "status": "interrupted",
                "next": next_nodes,
                "interrupts": pending_interrupts,
                "message": "run is waiting for human feedback; call resume_run_with_feedback",
            }
        if not next_nodes:
            values = _to_jsonable(getattr(snapshot, "values", {}) or {})
            return {
                "project_id": pid,
                "status": "completed",
                "message": "run already completed",
                "result": render_result(values if isinstance(values, dict) else {}),
                "state": values,
            }
        result = compiled_graph.invoke(None, config)
        return _format_run_result(pid, result)

    @mcp.tool()
    def resume_run_with_feedback(project_id: str, human_feedback: dict[str, Any] | str) -> dict[str, Any]:
        """
        Resume an interrupted run with human feedback payload.
        """
        pid = str(project_id or "").strip()
        if not pid:
            raise ValueError("project_id must not be empty")
        compiled_graph = get_compiled_graph()
        config = {"configurable": {"thread_id": pid}}
        result = compiled_graph.invoke(Command(resume=human_feedback), config)
        return _format_run_result(pid, result)


def main() -> None:  # pragma: no cover
    if FastMCP is None:
        raise RuntimeError(
            "fastmcp is not installed. Install with: pip install fastmcp\n"
            f"import error: {_IMPORT_ERROR}"
        )
    # Keep startup compatible with both official mcp SDK and Prefect fastmcp.
    run_params = inspect.signature(mcp.run).parameters
    kwargs: dict[str, Any] = {"transport": "stdio"}
    if "show_banner" in run_params:
        kwargs["show_banner"] = False
    if "log_level" in run_params:
        kwargs["log_level"] = "ERROR"
    mcp.run(**kwargs)


if __name__ == "__main__":  # pragma: no cover
    main()
