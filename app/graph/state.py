from typing import Any, Literal

from typing_extensions import TypedDict


class ProjectState(TypedDict, total=False):
    project_id: str
    thread_id: str
    raw_requirement: str
    requirement_doc: dict[str, Any]
    feasibility_report: dict[str, Any]
    architecture_plan: dict[str, Any]
    task_breakdown: list[dict[str, Any]]
    prompt_pack: list[dict[str, Any]]
    task_dependency_diagnostics: dict[str, Any]
    review_report: dict[str, Any]
    human_feedback_notes: list[Any]
    project_decisions: dict[str, Any]
    assumption_pack: dict[str, Any]
    human_rounds: int
    max_human_rounds: int
    review_rounds: int
    max_review_rounds: int
    next_step: Literal[
        "supervisor",
        "requirement_analyst",
        "feasibility_analyst",
        "architect",
        "planner",
        "prompt_builder",
        "reviewer",
        "human_gate",
        "finish",
    ]
    need_human: bool
    errors: list[str]
