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


class FakeMediumFeasibilityAgent:
    def invoke(self, _payload):
        return {
            "structured_response": FeasibilityReport(
                feasible=True,
                complexity="M",
                missing_info=[
                    "审批流具体规则未明确",
                    "折旧计算标准未确认",
                    "通知渠道优先级未明确",
                    "外部系统集成范围未明确",
                ],
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


def test_medium_requirement_enters_human_gate_by_dynamic_threshold(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.feasibility_analyst.build_feasibility_agent",
        lambda: FakeMediumFeasibilityAgent(),
    )
    state = {
        "requirement_doc": {"summary": "medium-demo"},
        "errors": [],
        "human_rounds": 0,
        "max_human_rounds": 3,
    }

    result = feasibility_analyst_node(state)
    assert result["need_human"] is True
    assert result["next_step"] == "human_gate"
    signal = result["feasibility_report"]["diagnostics"]["human_gate"]["missing_info_signal"]
    assert signal["dynamic_threshold"] == 4.0
    assert signal["missing_score"] >= signal["dynamic_threshold"]
