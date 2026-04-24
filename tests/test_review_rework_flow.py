from app.agents.schemas import PlannerOutput, PromptPackOutput, PromptTask, TaskItem
from app.graph.nodes.planner import planner_node
from app.graph.nodes.prompt_builder import prompt_builder_node


def test_planner_includes_review_feedback_on_rework(monkeypatch):
    captured = {"content": ""}

    class FakePlannerAgent:
        def invoke(self, payload):
            captured["content"] = payload["messages"][0]["content"]
            return {
                "structured_response": PlannerOutput(
                    milestones=["M1"],
                    tasks=[
                        TaskItem(
                            title="t1",
                            description="d1",
                            priority="P1",
                            depends_on=[],
                            owner_role="后端",
                        )
                    ],
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.planner.build_planner_agent",
        lambda: FakePlannerAgent(),
    )

    state = {
        "requirement_doc": {"summary": "s", "constraints": ["c1"]},
        "architecture_plan": {
            "architecture_style": "mono",
            "backend": ["python"],
            "frontend": ["vue"],
            "modules": [],
        },
        "review_rounds": 1,
        "review_report": {
            "passed": False,
            "issues": ["缺少物流任务"],
            "suggestions": ["补充发货状态流转"],
        },
        "next_step": "planner",
    }

    result = planner_node(state)
    assert result["next_step"] == "prompt_builder"
    assert "回流修复模式" in captured["content"]
    assert "缺少物流任务" in captured["content"]


def test_prompt_builder_includes_review_feedback_on_rework(monkeypatch):
    captured = {"content": ""}

    class FakePromptAgent:
        def invoke(self, payload):
            captured["content"] = payload["messages"][0]["content"]
            return {
                "structured_response": PromptPackOutput(
                    prompts=[
                        PromptTask(
                            task_title="t1",
                            coding_prompt="cp",
                            test_prompt="tp",
                        )
                    ]
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.prompt_builder.build_prompt_builder_agent",
        lambda: FakePromptAgent(),
    )

    state = {
        "task_breakdown": [
            {"title": "t1", "priority": "P1", "owner_role": "后端", "depends_on": []}
        ],
        "review_rounds": 1,
        "review_report": {
            "passed": False,
            "issues": ["读写分离风险未覆盖"],
            "suggestions": ["增加主从延迟回源测试"],
        },
        "next_step": "prompt_builder",
    }

    result = prompt_builder_node(state)
    assert result["next_step"] == "reviewer"
    assert "回流修复模式" in captured["content"]
    assert "读写分离风险未覆盖" in captured["content"]

