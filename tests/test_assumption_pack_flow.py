from app.agents.schemas import PlannerOutput, ReviewReport, TaskItem
from app.graph.nodes.planner import planner_node
from app.graph.nodes.reviewer import reviewer_node


class FakeMinimalPlannerAgent:
    def invoke(self, _payload):
        return {
            "structured_response": PlannerOutput(
                tasks=[
                    TaskItem(
                        title="实现核心流程",
                        description="实现当前MVP核心流程。",
                        priority="P0",
                        depends_on=[],
                        owner_role="后端",
                    ),
                    TaskItem(
                        title="高级分析报表开发",
                        description="实现高级分析报表。",
                        priority="P2",
                        depends_on=[],
                        owner_role="后端",
                    ),
                ]
            )
        }


class FakePassingReviewerAgent:
    def invoke(self, _payload):
        return {
            "structured_response": ReviewReport(
                passed=True,
                issues=[],
                suggestions=[],
            )
        }


def test_planner_adds_assumption_tasks_and_excludes_deferred_scope(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.planner.build_planner_agent",
        lambda: FakeMinimalPlannerAgent(),
    )
    state = {
        "requirement_doc": {"summary": "业务系统", "constraints": []},
        "feasibility_report": {"risks": []},
        "architecture_plan": {
            "architecture_style": "模块化单体",
            "backend": ["Python"],
            "frontend": ["Vue"],
            "modules": [],
        },
        "assumption_pack": {
            "human_gate_exhausted": True,
            "unresolved_missing_info": ["外部服务接口服务等级未明确"],
            "blocking": [],
            "assumptions": [
                {
                    "source": "外部服务接口服务等级未明确",
                    "assumption": "按可重试、可降级和人工兜底策略继续。",
                }
            ],
            "risk_controls": [
                {
                    "missing_info": "外部服务接口服务等级未明确",
                    "control": "提供适配器、mock、重试、降级与人工处理边界。",
                }
            ],
            "deferred_scope": ["高级分析报表"],
            "requires_user_confirmation": [
                {"item": "外部服务接口服务等级未明确", "phase": "上线前确认"}
            ],
        },
        "review_report": {},
        "review_rounds": 0,
        "project_decisions": {},
    }

    result = planner_node(state)
    titles = [item["title"] for item in result["task_breakdown"]]
    all_text = " ".join(f"{item['title']} {item['description']}" for item in result["task_breakdown"])

    assert "验证关键假设与替代方案" in titles
    assert "落实受控假设的风险控制措施" in titles
    assert "上线前确认清单与决策复核" in titles
    assert "高级分析报表" not in all_text


def test_reviewer_blocks_uncontrolled_assumption_pack(monkeypatch):
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: FakePassingReviewerAgent(),
    )
    state = {
        "requirement_doc": {"summary": "业务系统", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "模块化单体", "backend": [], "frontend": []},
        "task_breakdown": [
            {"title": "实现核心流程", "description": "实现核心流程", "priority": "P0", "depends_on": []}
        ],
        "prompt_pack": [{"task_title": "实现核心流程", "coding_prompt": "a", "test_prompt": "b"}],
        "assumption_pack": {
            "human_gate_exhausted": True,
            "blocking": [],
            "assumptions": [{"source": "外部服务接口服务等级未明确"}],
            "risk_controls": [{"missing_info": "外部服务接口服务等级未明确"}],
            "deferred_scope": [],
            "requires_user_confirmation": [{"item": "外部服务接口服务等级未明确"}],
        },
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)

    assert result["next_step"] == "planner"
    assert result["review_report"]["passed"] is False
    assert any("受控假设" in issue for issue in result["review_report"]["issues"])


def test_reviewer_allows_controlled_scope_reduction_for_exhausted_blocking_info(monkeypatch):
    agent = FakePassingReviewerAgent()
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: agent,
    )
    state = {
        "requirement_doc": {"summary": "业务系统", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "模块化单体", "backend": [], "frontend": []},
        "task_breakdown": [
            {"title": "验证关键假设与替代方案", "description": "验证替代方案", "priority": "P0", "depends_on": []},
            {"title": "上线前确认清单与决策复核", "description": "确认范围收缩", "priority": "P0", "depends_on": []},
        ],
        "prompt_pack": [
            {"task_title": "验证关键假设与替代方案", "coding_prompt": "a", "test_prompt": "b"},
            {"task_title": "上线前确认清单与决策复核", "coding_prompt": "a", "test_prompt": "b"},
        ],
        "assumption_pack": {
            "human_gate_exhausted": True,
            "blocking": ["核心外部依赖协议未明确"],
            "scope_reductions": [
                {
                    "missing_info": "核心外部依赖协议未明确",
                    "action": "将依赖实时联调收缩为适配器、mock和替代方案验证。",
                }
            ],
            "assumptions": [],
            "risk_controls": [],
            "deferred_scope": [],
            "requires_user_confirmation": [{"item": "核心外部依赖协议未明确"}],
        },
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)

    assert result["next_step"] == "finish"
    assert result["review_report"]["passed"] is True
