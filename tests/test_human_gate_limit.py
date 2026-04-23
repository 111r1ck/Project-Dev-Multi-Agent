from app.agents.schemas import FeasibilityReport
from app.graph.nodes.feasibility_analyst import feasibility_analyst_node


class FakeFeasibilityAgent:
    def invoke(self, _payload):
        return {
            "structured_response": FeasibilityReport(
                feasible=True,
                complexity="high",
                missing_info=["a", "b", "c", "d"],
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
