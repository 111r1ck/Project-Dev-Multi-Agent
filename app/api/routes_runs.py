from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from app.dependencies import get_compiled_graph
from app.services.report_renderer import render_result
from app.config import settings
from langgraph.types import Command

router = APIRouter(prefix="/runs", tags=["runs"])


class RunRequest(BaseModel):
    project_id: str
    raw_requirement: str


class ResumeRunRequest(BaseModel):
    human_feedback: dict[str, Any] | str


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
    if "__interrupt__" in result:
        interrupts = []
        for item in result["__interrupt__"]:
            interrupts.append(_serialize_interrupt(item))

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


@router.post("")
async def run_project_analysis(
    req: RunRequest,
    compiled_graph=Depends(get_compiled_graph),
):
    config = {"configurable": {"thread_id": req.project_id}}
    result = compiled_graph.invoke(
        {
            "project_id": req.project_id,
            "thread_id": req.project_id,
            "raw_requirement": req.raw_requirement,
            "errors": [],
            "need_human": False,
            "human_rounds": 0,
            "max_human_rounds": settings.human_gate_max_rounds,
            "next_step": "requirement_analyst",
        },
        config=config,
    )

    return _format_run_response(req.project_id, result)


@router.post("/{project_id}/resume")
async def resume_project_analysis(
    project_id: str,
    req: ResumeRunRequest,
    compiled_graph=Depends(get_compiled_graph),
):
    config = {"configurable": {"thread_id": project_id}}
    result = compiled_graph.invoke(Command(resume=req.human_feedback), config=config)
    return _format_run_response(project_id, result)


@router.get("/{project_id}/state")
async def get_project_run_state(
    project_id: str,
    compiled_graph=Depends(get_compiled_graph),
):
    config = {"configurable": {"thread_id": project_id}}
    snapshot = compiled_graph.get_state(config)
    state = _serialize_snapshot(snapshot)
    return {
        "project_id": project_id,
        "values": state["values"],
        "next": state["next"],
        "created_at": state["created_at"],
        "checkpoint_id": state["checkpoint_id"],
        "metadata": state["metadata"],
    }


@router.get("/{project_id}/history")
async def get_project_run_history(
    project_id: str,
    limit: int = Query(20, ge=1, le=200),
    compiled_graph=Depends(get_compiled_graph),
):
    config = {"configurable": {"thread_id": project_id}}
    snapshots = list(compiled_graph.get_state_history(config, limit=limit))
    return {
        "project_id": project_id,
        "count": len(snapshots),
        "history": [_serialize_snapshot(snapshot) for snapshot in snapshots],
    }
