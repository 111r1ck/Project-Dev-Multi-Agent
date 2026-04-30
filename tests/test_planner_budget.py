from app.agents.schemas import PlannerOutput, TaskItem
from app.graph.nodes.planner import planner_node


class FakeManyTasksPlannerAgent:
    def __init__(self, total: int):
        self.total = total

    def invoke(self, _payload):
        tasks = []
        for idx in range(1, self.total + 1):
            tasks.append(
                TaskItem(
                    title=f"任务{idx}",
                    description=f"描述{idx}",
                    priority="P1",
                    depends_on=[],
                    owner_role="后端",
                )
            )
        return {"structured_response": PlannerOutput(tasks=tasks)}


class FakeMixedPriorityPlannerAgent:
    def invoke(self, _payload):
        tasks = [
            TaskItem(
                title="P0主链路任务",
                description="关键链路",
                priority="P0",
                depends_on=[],
                owner_role="后端",
            ),
            TaskItem(
                title="P1实现任务",
                description="常规实现",
                priority="P1",
                depends_on=[],
                owner_role="后端",
            ),
        ]
        for idx in range(1, 8):
            tasks.append(
                TaskItem(
                    title=f"P2优化任务{idx}",
                    description="可后置优化",
                    priority="P2",
                    depends_on=[],
                    owner_role="后端",
                )
            )
        return {"structured_response": PlannerOutput(tasks=tasks)}


def _base_state() -> dict:
    return {
        "requirement_doc": {"summary": "simple", "constraints": []},
        "feasibility_report": {"complexity": "low", "risks": []},
        "architecture_plan": {
            "architecture_style": "mono",
            "backend": ["python"],
            "frontend": ["vue"],
            "modules": [],
        },
        "review_report": {},
        "project_decisions": {},
    }


def test_planner_limits_task_count_for_simple_requirement(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.planner.build_planner_agent",
        lambda: FakeManyTasksPlannerAgent(total=30),
    )
    state = _base_state()
    state["review_rounds"] = 0

    result = planner_node(state)
    assert len(result["task_breakdown"]) <= 12


def test_planner_rework_round_should_not_grow_task_count(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.planner.build_planner_agent",
        lambda: FakeManyTasksPlannerAgent(total=20),
    )
    state = _base_state()
    state["review_rounds"] = 1
    state["review_report"] = {"passed": False, "issues": ["关键阻塞问题"], "suggestions": []}
    state["task_breakdown"] = [
        {
            "title": f"旧任务{i}",
            "description": "旧描述",
            "priority": "P1",
            "depends_on": [],
            "owner_role": "后端开发工程师",
        }
        for i in range(1, 9)
    ]

    result = planner_node(state)
    assert len(result["task_breakdown"]) <= 8


def test_planner_defers_most_low_priority_tasks(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.planner.build_planner_agent",
        lambda: FakeMixedPriorityPlannerAgent(),
    )
    state = _base_state()
    state["review_rounds"] = 0

    result = planner_node(state)
    low_priority = [
        item for item in result["task_breakdown"] if str(item.get("priority", "")).upper() in {"P2", "P3"}
    ]
    assert len(low_priority) <= 1
