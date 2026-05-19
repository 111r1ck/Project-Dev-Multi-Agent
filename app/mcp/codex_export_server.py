from __future__ import annotations

import inspect
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.dependencies import get_compiled_graph
from app.services.export_service import (
    SUPPORTED_EXPORT_FORMATS,
    SUPPORTED_EXPORT_SECTIONS,
    export_run_artifact,
)

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


if FastMCP is not None:
    mcp = FastMCP("multi-agent-export")

    @mcp.tool()
    def list_export_capabilities() -> dict[str, Any]:
        """List export formats and sections supported by this project."""
        return {
            "formats": sorted(SUPPORTED_EXPORT_FORMATS),
            "sections": sorted(SUPPORTED_EXPORT_SECTIONS),
            "mode": "persist_only",
            "note": "Use export_run_artifact to write files under exports/{project_id}/",
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
