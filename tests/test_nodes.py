from app.agents.schemas import RequirementDoc
from app.graph.nodes.requirement_analyst import requirement_analyst_node


class FakeRequirementAgent:
    def invoke(self, _payload):
        return {
            "structured_response": RequirementDoc(
                project_name="demo",
                summary="summary",
            )
        }


def test_requirement_node_smoke(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.requirement_analyst.build_requirement_agent",
        lambda: FakeRequirementAgent(),
    )
    state = {
        "raw_requirement": "做一个电商系统，支持登录、商品、订单。",
        "errors": [],
        "need_human": False,
        "next_step": "requirement_analyst",
    }

    result = requirement_analyst_node(state)
    assert "requirement_doc" in result
    assert result["next_step"] == "feasibility_analyst"
