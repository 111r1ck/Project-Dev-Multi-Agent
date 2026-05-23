import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.dependencies import get_compiled_graph
from app.services.export_service import (
    SUPPORTED_EXPORT_FORMATS,
    SUPPORTED_EXPORT_SECTIONS,
    build_run_export_content,
    export_run_artifact,
)
from app.services.report_renderer import render_result
from app.config import settings
from app.storage.checkpoints import purge_thread_checkpoints
from langgraph.types import Command

router = APIRouter(prefix="/runs", tags=["runs"])
_CONTINUE_JOBS: dict[str, threading.Thread] = {}
_CONTINUE_JOBS_LOCK = threading.RLock()
_CONTINUE_JOB_STATUS: dict[str, dict[str, Any]] = {}
_RUNNING_PROJECTS: set[str] = set()


class RunRequest(BaseModel):
    project_id: str
    raw_requirement: str


class ResumeRunRequest(BaseModel):
    human_feedback: dict[str, Any] | str


class ExportRunRequest(BaseModel):
    format: str = "json"
    sections: list[str] = [
        "summary",
        "requirement_doc",
        "feasibility_report",
        "architecture_plan",
        "tasks",
        "prompts",
        "review",
        "diagnostics",
    ]


def _try_acquire_project_run(project_id: str) -> bool:
    with _CONTINUE_JOBS_LOCK:
        if project_id in _RUNNING_PROJECTS:
            return False
        _RUNNING_PROJECTS.add(project_id)
        return True


def _release_project_run(project_id: str) -> None:
    with _CONTINUE_JOBS_LOCK:
        _RUNNING_PROJECTS.discard(project_id)


def _serialize_interrupt(item: Any) -> Any:
    value = getattr(item, "value", None)
    return value if value is not None else str(item)


def _serialize_task(task: Any) -> dict[str, Any]:
    return {
        "id": getattr(task, "id", None),
        "name": getattr(task, "name", None),
        "error": str(getattr(task, "error", "")) if getattr(task, "error", None) else None,
        "interrupts": [_serialize_interrupt(i) for i in getattr(task, "interrupts", ())],
    }


def _serialize_snapshot(snapshot: Any) -> dict[str, Any]:
    config = getattr(snapshot, "config", {}) or {}
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    metadata = getattr(snapshot, "metadata", {}) or {}
    created_at = getattr(snapshot, "created_at", None)
    if created_at is not None and not isinstance(created_at, str):
        created_at = created_at.isoformat()

    return {
        "checkpoint_id": configurable.get("checkpoint_id"),
        "checkpoint_ns": configurable.get("checkpoint_ns"),
        "thread_id": configurable.get("thread_id"),
        "created_at": created_at,
        "next": list(getattr(snapshot, "next", ()) or ()),
        "metadata": jsonable_encoder(metadata),
        "values": jsonable_encoder(getattr(snapshot, "values", {}) or {}),
        "tasks": [_serialize_task(t) for t in (getattr(snapshot, "tasks", ()) or ())],
    }


def _format_run_response(project_id: str, result: dict[str, Any]) -> dict[str, Any]:
    raw_interrupts = result.get("__interrupt__", [])
    interrupts = []
    for item in raw_interrupts or []:
        interrupts.append(_serialize_interrupt(item))

    if interrupts:
        return {
            "project_id": project_id,
            "status": "interrupted",
            "interrupts": interrupts,
            "state": result,
        }

    return {
        "project_id": project_id,
        "status": "completed",
        "result": render_result(result),
        "state": result,
    }


def _snapshot_has_pending_interrupt(snapshot: Any) -> bool:
    tasks = getattr(snapshot, "tasks", ()) or ()
    for task in tasks:
        if getattr(task, "interrupts", ()) or ():
            return True
    return False


def _extract_pending_interrupts_from_snapshot(snapshot: Any) -> list[Any]:
    pending: list[Any] = []
    tasks = getattr(snapshot, "tasks", ()) or ()
    for task in tasks:
        for item in getattr(task, "interrupts", ()) or ():
            pending.append(_serialize_interrupt(item))
    return pending


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_continue_in_background(
    compiled_graph: Any,
    config: dict[str, Any],
    project_id: str,
    baseline_checkpoint_id: str | None,
) -> None:
    status = "completed"
    error: str | None = None
    latest_checkpoint_id: str | None = None
    latest_next: list[str] = []
    try:
        try:
            compiled_graph.invoke(None, config)
        except Exception as exc:
            status = "failed"
            error = str(exc)

        try:
            latest_snapshot = compiled_graph.get_state(config)
            latest_checkpoint_id = (
                (getattr(latest_snapshot, "config", {}) or {})
                .get("configurable", {})
                .get("checkpoint_id")
            )
            latest_next = list(getattr(latest_snapshot, "next", ()) or ())
            # If checkpoint does not advance and workflow still has next nodes,
            # continue likely did not make effective progress.
            if (
                status == "completed"
                and baseline_checkpoint_id is not None
                and latest_checkpoint_id == baseline_checkpoint_id
                and latest_next
            ):
                status = "no_progress"
                error = "后台继续执行未推进到新checkpoint，请检查日志或重试。"
        except Exception as snapshot_exc:
            if status == "completed":
                status = "failed"
                error = f"继续执行后读取状态失败: {snapshot_exc}"
    finally:
        _release_project_run(project_id)
        with _CONTINUE_JOBS_LOCK:
            _CONTINUE_JOB_STATUS[project_id] = {
                "status": status,
                "error": error,
                "baseline_checkpoint_id": baseline_checkpoint_id,
                "latest_checkpoint_id": latest_checkpoint_id,
                "latest_next": latest_next,
                "finished_at": _now_iso(),
            }
            current = _CONTINUE_JOBS.get(project_id)
            if current is threading.current_thread():
                _CONTINUE_JOBS.pop(project_id, None)


@router.post("")
async def run_project_analysis(
    req: RunRequest,
    compiled_graph=Depends(get_compiled_graph),
):
    if not _try_acquire_project_run(req.project_id):
        raise HTTPException(
            status_code=409,
            detail="当前项目已有执行中的 run/resume/continue 请求，请稍后重试。",
        )
    config = {"configurable": {"thread_id": req.project_id}}
    preserved_term_cluster_memory: dict[str, Any] = {}
    try:
        try:
            snapshot = await run_in_threadpool(compiled_graph.get_state, config)
            values = jsonable_encoder(getattr(snapshot, "values", {}) or {})
            memory = values.get("term_cluster_memory", {})
            if isinstance(memory, dict):
                preserved_term_cluster_memory = memory
        except Exception:
            preserved_term_cluster_memory = {}

        result = await run_in_threadpool(
            compiled_graph.invoke,
            {
                "project_id": req.project_id,
                "thread_id": req.project_id,
                "raw_requirement": req.raw_requirement,
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
        with _CONTINUE_JOBS_LOCK:
            _CONTINUE_JOB_STATUS.pop(req.project_id, None)

        return _format_run_response(req.project_id, result)
    finally:
        _release_project_run(req.project_id)


@router.post("/{project_id}/resume")
async def resume_project_analysis(
    project_id: str,
    req: ResumeRunRequest,
    compiled_graph=Depends(get_compiled_graph),
):
    if not _try_acquire_project_run(project_id):
        raise HTTPException(
            status_code=409,
            detail="当前项目已有执行中的 run/resume/continue 请求，请稍后重试。",
        )
    config = {"configurable": {"thread_id": project_id}}
    try:
        result = await run_in_threadpool(
            compiled_graph.invoke,
            Command(resume=req.human_feedback),
            config,
        )
        with _CONTINUE_JOBS_LOCK:
            _CONTINUE_JOB_STATUS.pop(project_id, None)
        return _format_run_response(project_id, result)
    finally:
        _release_project_run(project_id)


@router.post("/{project_id}/continue")
async def continue_project_analysis(
    project_id: str,
    compiled_graph=Depends(get_compiled_graph),
):
    config = {"configurable": {"thread_id": project_id}}
    snapshot = await run_in_threadpool(compiled_graph.get_state, config)
    next_nodes = list(getattr(snapshot, "next", ()) or ())

    if _snapshot_has_pending_interrupt(snapshot):
        return {
            "project_id": project_id,
            "status": "interrupted",
            "message": "当前流程处于人工中断等待状态，请调用 /runs/{project_id}/resume 继续。",
            "next": next_nodes,
        }

    if not next_nodes:
        values = jsonable_encoder(getattr(snapshot, "values", {}) or {})
        return {
            "project_id": project_id,
            "status": "completed",
            "message": "流程已完成，无需继续执行。",
            "result": render_result(values),
            "state": values,
        }

    with _CONTINUE_JOBS_LOCK:
        running_job = _CONTINUE_JOBS.get(project_id)
        if running_job is not None and running_job.is_alive():
            return {
                "project_id": project_id,
                "status": "in_progress",
                "next": next_nodes,
                "message": "已有继续执行任务在后台运行，请稍后刷新 state/history。",
            }

        previous_status = _CONTINUE_JOB_STATUS.get(project_id)
        if previous_status and previous_status.get("status") == "failed":
            return {
                "project_id": project_id,
                "status": "failed",
                "next": next_nodes,
                "message": "上一次后台继续执行失败，请查看错误并重试。",
                "error": previous_status.get("error"),
            }
        if previous_status and previous_status.get("status") == "no_progress":
            return {
                "project_id": project_id,
                "status": "failed",
                "next": next_nodes,
                "message": "上一次后台继续执行未推进流程，请检查后重试。",
                "error": previous_status.get("error"),
            }

        if project_id in _RUNNING_PROJECTS:
            return {
                "project_id": project_id,
                "status": "in_progress",
                "next": next_nodes,
                "message": "当前项目已有执行中的 run/resume/continue 请求，请稍后重试。",
            }

        _RUNNING_PROJECTS.add(project_id)
        baseline_checkpoint_id = (
            (getattr(snapshot, "config", {}) or {})
            .get("configurable", {})
            .get("checkpoint_id")
        )
        _CONTINUE_JOB_STATUS[project_id] = {
            "status": "running",
            "error": None,
            "baseline_checkpoint_id": baseline_checkpoint_id,
            "started_at": _now_iso(),
        }
        job = threading.Thread(
            target=_run_continue_in_background,
            args=(compiled_graph, config, project_id, baseline_checkpoint_id),
            daemon=True,
            name=f"continue-{project_id}",
        )
        _CONTINUE_JOBS[project_id] = job
        job.start()

    return {
        "project_id": project_id,
        "status": "in_progress",
        "next": next_nodes,
        "message": "已在后台继续执行，请稍后刷新 state/history。",
    }


@router.get("/{project_id}/state")
async def get_project_run_state(
    project_id: str,
    compiled_graph=Depends(get_compiled_graph),
):
    config = {"configurable": {"thread_id": project_id}}
    snapshot = await run_in_threadpool(compiled_graph.get_state, config)
    state = _serialize_snapshot(snapshot)
    pending_interrupts = _extract_pending_interrupts_from_snapshot(snapshot)
    with _CONTINUE_JOBS_LOCK:
        continue_status = dict(_CONTINUE_JOB_STATUS.get(project_id, {}))
        running_job = _CONTINUE_JOBS.get(project_id)
        continue_alive = bool(running_job and running_job.is_alive())
    return {
        "project_id": project_id,
        "values": state["values"],
        "next": state["next"],
        "created_at": state["created_at"],
        "checkpoint_id": state["checkpoint_id"],
        "metadata": state["metadata"],
        "tasks": state["tasks"],
        "has_pending_interrupt": bool(pending_interrupts),
        "pending_interrupts": pending_interrupts,
        "continue_status": continue_status,
        "continue_alive": continue_alive,
    }


@router.get("/{project_id}/history")
async def get_project_run_history(
    project_id: str,
    limit: int = Query(20, ge=1, le=200),
    compiled_graph=Depends(get_compiled_graph),
):
    config = {"configurable": {"thread_id": project_id}}
    snapshots = await run_in_threadpool(
        lambda: list(compiled_graph.get_state_history(config, limit=limit))
    )
    return {
        "project_id": project_id,
        "count": len(snapshots),
        "history": [_serialize_snapshot(snapshot) for snapshot in snapshots],
    }


@router.delete("/{project_id}/checkpoints")
async def delete_project_checkpoints(project_id: str):
    try:
        result = await run_in_threadpool(purge_thread_checkpoints, project_id)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"删除 checkpoints 失败: {type(exc).__name__}: {exc}",
        ) from exc
    return {
        "project_id": project_id,
        "status": "deleted",
        **result,
    }


@router.post("/{project_id}/export")
async def export_project_run_result(
    project_id: str,
    req: ExportRunRequest,
    compiled_graph=Depends(get_compiled_graph),
):
    fmt = str(req.format or "").strip().lower()
    if fmt not in SUPPORTED_EXPORT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的导出格式: {fmt}; 支持: {sorted(SUPPORTED_EXPORT_FORMATS)}",
        )
    sections = [str(item or "").strip().lower() for item in (req.sections or []) if str(item or "").strip()]
    if not sections:
        raise HTTPException(status_code=400, detail="sections 不能为空")
    invalid = [item for item in sections if item not in SUPPORTED_EXPORT_SECTIONS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的 sections: {invalid}; 支持: {sorted(SUPPORTED_EXPORT_SECTIONS)}",
        )

    config = {"configurable": {"thread_id": project_id}}
    snapshot = await run_in_threadpool(compiled_graph.get_state, config)
    values = jsonable_encoder(getattr(snapshot, "values", {}) or {})
    if not values:
        raise HTTPException(status_code=404, detail="未找到可导出的运行结果")

    exported = await run_in_threadpool(
        export_run_artifact,
        project_id=project_id,
        values=values,
        export_format=fmt,
        sections=sections,
    )
    return {
        "project_id": project_id,
        "status": "exported",
        **exported,
    }


@router.get("/{project_id}/export/download")
async def download_project_run_result(
    project_id: str,
    format: str = Query("json"),
    sections: str = Query("summary,requirement_doc,feasibility_report,architecture_plan,tasks,prompts,review,diagnostics"),
    compiled_graph=Depends(get_compiled_graph),
):
    fmt = str(format or "").strip().lower()
    if fmt not in SUPPORTED_EXPORT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的导出格式: {fmt}; 支持: {sorted(SUPPORTED_EXPORT_FORMATS)}",
        )
    raw_sections = [s.strip().lower() for s in str(sections or "").split(",") if s.strip()]
    if not raw_sections:
        raise HTTPException(status_code=400, detail="sections 不能为空")
    invalid = [item for item in raw_sections if item not in SUPPORTED_EXPORT_SECTIONS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的 sections: {invalid}; 支持: {sorted(SUPPORTED_EXPORT_SECTIONS)}",
        )

    config = {"configurable": {"thread_id": project_id}}
    snapshot = await run_in_threadpool(compiled_graph.get_state, config)
    values = jsonable_encoder(getattr(snapshot, "values", {}) or {})
    if not values:
        raise HTTPException(status_code=404, detail="未找到可导出的运行结果")

    content = await run_in_threadpool(
        build_run_export_content,
        project_id=project_id,
        values=values,
        export_format=fmt,
        sections=raw_sections,
    )
    headers = {
        "Content-Disposition": f'attachment; filename="{content["filename"]}"',
        "X-Export-SHA256": str(content["sha256"]),
    }
    return {
        "project_id": project_id,
        "status": "download_ready",
        "format": fmt,
        "sections": raw_sections,
        "filename": content["filename"],
        "mime_type": content["mime_type"],
        "size_bytes": content["size_bytes"],
        "sha256": content["sha256"],
        "download_url": (
            f"/runs/{project_id}/export/file"
            f"?format={fmt}&sections={','.join(raw_sections)}"
        ),
    }


@router.get("/{project_id}/export/file")
async def download_project_run_result_file(
    project_id: str,
    format: str = Query("json"),
    sections: str = Query("summary,requirement_doc,feasibility_report,architecture_plan,tasks,prompts,review,diagnostics"),
    compiled_graph=Depends(get_compiled_graph),
):
    fmt = str(format or "").strip().lower()
    if fmt not in SUPPORTED_EXPORT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的导出格式: {fmt}; 支持: {sorted(SUPPORTED_EXPORT_FORMATS)}",
        )
    raw_sections = [s.strip().lower() for s in str(sections or "").split(",") if s.strip()]
    if not raw_sections:
        raise HTTPException(status_code=400, detail="sections 不能为空")
    invalid = [item for item in raw_sections if item not in SUPPORTED_EXPORT_SECTIONS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的 sections: {invalid}; 支持: {sorted(SUPPORTED_EXPORT_SECTIONS)}",
        )
    config = {"configurable": {"thread_id": project_id}}
    snapshot = await run_in_threadpool(compiled_graph.get_state, config)
    values = jsonable_encoder(getattr(snapshot, "values", {}) or {})
    if not values:
        raise HTTPException(status_code=404, detail="未找到可导出的运行结果")
    content = await run_in_threadpool(
        build_run_export_content,
        project_id=project_id,
        values=values,
        export_format=fmt,
        sections=raw_sections,
    )
    headers = {
        "Content-Disposition": f'attachment; filename="{content["filename"]}"',
        "X-Export-SHA256": str(content["sha256"]),
    }
    return Response(
        content=content["bytes"],
        media_type=str(content["mime_type"]),
        headers=headers,
    )
