from app.agents.architect_agent import build_architect_agent
from app.graph.nodes.common import compact_json, extract_structured_response
from app.graph.state import ProjectState


_LANGUAGE_MARKERS = (
    ("python", "fastapi", "flask", "django"),
    ("java", "spring"),
    ("go", "golang"),
    ("node", "typescript", "nestjs", "express"),
    ("c#", ".net", "dotnet"),
)


def _language_group(item: str) -> int | None:
    normalized = item.lower()
    for idx, markers in enumerate(_LANGUAGE_MARKERS):
        if any(marker in normalized for marker in markers):
            return idx
    return None


def _normalize_backend_stack(backend: list) -> list[str]:
    normalized_items = [str(item).strip() for item in (backend or []) if str(item).strip()]
    primary_language: int | None = None
    result: list[str] = []
    for item in normalized_items:
        group = _language_group(item)
        if group is None:
            if item not in result:
                result.append(item)
            continue
        if primary_language is None:
            primary_language = group
            result.append(item)
            continue
        if group == primary_language and item not in result:
            result.append(item)
    return result


def _normalize_architecture_plan(plan: dict) -> dict:
    plan = dict(plan)
    backend = plan.get("backend", []) or []
    plan["backend"] = _normalize_backend_stack(backend)
    style = str(plan.get("architecture_style", "") or "")
    if not plan["backend"] and "前后端分离" in style:
        if "Client-Side Only SPA" in style:
            plan["architecture_style"] = "本地优先的模块化前端单体架构 (Client-Side Only SPA)"
        else:
            plan["architecture_style"] = style.replace("前后端分离", "纯前端").strip()
    return plan


def architect_node(state: ProjectState) -> ProjectState:
    req = state["requirement_doc"]
    fea = state["feasibility_report"]
    assumption_pack = state.get("assumption_pack", {})
    compact_context = (
        "请基于以下摘要生成架构方案。\n"
        f"需求摘要: {req.get('summary', '')}\n"
        f"角色: {compact_json(req.get('roles', []), max_chars=800)}\n"
        f"模块: {compact_json(req.get('modules', []), max_chars=1000)}\n"
        f"约束: {compact_json(req.get('constraints', []), max_chars=1200)}\n"
        f"可行性: feasible={fea.get('feasible')} complexity={fea.get('complexity')}\n"
        f"主要风险: {compact_json(fea.get('risks', [])[:5], max_chars=1200)}\n"
        f"MVP范围: {compact_json(fea.get('mvp_scope', [])[:8], max_chars=1200)}\n"
        f"受控假设包: {compact_json(assumption_pack, max_chars=1600)}\n"
        "若存在受控假设，请不要把假设写成用户硬约束；"
        "请体现风险控制和扩展点，并避免将后置范围纳入MVP架构。"
    )

    agent = build_architect_agent()
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": compact_context,
                }
            ]
        }
    )
    structured = extract_structured_response(result)
    plan = _normalize_architecture_plan(structured.model_dump())

    return {
        **state,
        "architecture_plan": plan,
        "next_step": "planner",
    }
