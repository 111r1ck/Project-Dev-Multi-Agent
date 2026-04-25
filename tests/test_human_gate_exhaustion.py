from app.agents.schemas import FeasibilityReport
from app.graph.nodes.feasibility_analyst import feasibility_analyst_node


class FakeExhaustedFeasibilityAgent:
    def invoke(self, _payload):
        return {
            "structured_response": FeasibilityReport(
                feasible=False,
                complexity="high",
                missing_info=[
                    "外部服务接口服务等级未明确",
                    "高级分析报表口径未确认",
                ],
                risks=["信息不足"],
                mvp_scope=["核心流程"],
            )
        }


def test_human_gate_exhaustion_generates_assumption_pack(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.feasibility_analyst.build_feasibility_agent",
        lambda: FakeExhaustedFeasibilityAgent(),
    )
    state = {
        "requirement_doc": {"summary": "业务系统"},
        "human_feedback_notes": [],
        "project_decisions": {},
        "errors": [],
        "human_rounds": 3,
        "max_human_rounds": 3,
    }

    result = feasibility_analyst_node(state)

    assert result["need_human"] is False
    assert result["next_step"] == "architect"
    assert result["assumption_pack"]["human_gate_exhausted"] is True
    assert result["assumption_pack"]["unresolved_missing_info"] == [
        "外部服务接口服务等级未明确",
        "高级分析报表口径未确认",
    ]
    assert "受控假设" in result["errors"][-1]
