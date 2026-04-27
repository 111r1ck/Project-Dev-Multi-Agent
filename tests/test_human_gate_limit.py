from app.agents.schemas import FeasibilityReport
from app.graph.nodes.feasibility_analyst import feasibility_analyst_node


class FakeFeasibilityAgent:
    def invoke(self, _payload):
        return {
            "structured_response": FeasibilityReport(
                feasible=False,
                complexity="high",
                missing_info=["a", "b", "c", "d"],
            )
        }


class FakeSimpleFeasibilityAgent:
    def invoke(self, _payload):
        return {
            "structured_response": FeasibilityReport(
                feasible=True,
                complexity="low",
                missing_info=["部署环境未明确", "日志保留周期未明确", "备份窗口未明确"],
            )
        }


def test_human_gate_limit_forces_progress(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.feasibility_analyst.build_feasibility_agent",
        lambda: FakeFeasibilityAgent(),
    )
    state = {
        "requirement_doc": {"summary": "demo"},
        "errors": [],
        "human_rounds": 3,
        "max_human_rounds": 3,
    }
    result = feasibility_analyst_node(state)
    assert result["need_human"] is False
    assert result["next_step"] == "architect"
    assert "上限" in result["errors"][-1]


def test_simple_requirement_should_not_enter_human_gate_by_missing_count(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.feasibility_analyst.build_feasibility_agent",
        lambda: FakeSimpleFeasibilityAgent(),
    )
    state = {
        "requirement_doc": {"summary": "simple-demo"},
        "errors": [],
        "human_rounds": 0,
        "max_human_rounds": 3,
    }

    result = feasibility_analyst_node(state)
    assert result["need_human"] is False
    assert result["next_step"] == "architect"
