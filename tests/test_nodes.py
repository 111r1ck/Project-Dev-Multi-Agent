from app.agents.schemas import RequirementDoc
from app.agents.schemas import PlannerOutput, PromptPackOutput, PromptTask, ReviewReport, TaskItem
from app.graph.nodes.planner import planner_node
from app.graph.nodes.prompt_builder import prompt_builder_node
from app.graph.nodes.requirement_analyst import requirement_analyst_node
from app.graph.nodes.reviewer import reviewer_node


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


class FakePlannerAgent:
    def invoke(self, _payload):
        return {
            "structured_response": PlannerOutput(
                tasks=[
                    TaskItem(
                        title="基础项目初始化",
                        description="初始化仓库与目录结构",
                        priority="P0",
                        depends_on=[],
                        owner_role="后端开发工程师",
                    )
                ]
            )
        }


class FakePromptBuilderAgent:
    def invoke(self, _payload):
        return {
            "structured_response": PromptPackOutput(
                prompts=[
                    PromptTask(
                        task_title="任务A",
                        coding_prompt="实现A",
                        test_prompt="测试A",
                    )
                ]
            )
        }


class FakeReviewerAgent:
    def __init__(self, passed: bool = True):
        self.passed = passed
        self.calls = 0

    def invoke(self, _payload):
        self.calls += 1
        return {
            "structured_response": ReviewReport(
                passed=self.passed,
                issues=[] if self.passed else ["存在阻塞问题"],
                suggestions=[] if self.passed else ["请补齐任务"],
            )
        }


def test_planner_auto_fill_required_tasks(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.planner.build_planner_agent",
        lambda: FakePlannerAgent(),
    )
    state = {
        "requirement_doc": {
            "summary": "平台需对接外部系统并实现自动对账、智能摘要能力。",
            "modules": ["数据同步", "账务", "智能分析"],
            "constraints": ["成本超限自动降级", "离线缓存恢复机制"],
        },
        "architecture_plan": {
            "architecture_style": "模块化单体",
            "backend": ["Python"],
            "frontend": ["Vue"],
            "modules": [],
        },
        "review_report": {},
        "review_rounds": 0,
    }

    result = planner_node(state)
    titles = [item["title"] for item in result["task_breakdown"]]
    assert "基础项目初始化" in titles


def test_planner_auto_fill_missing_tasks_from_review(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.planner.build_planner_agent",
        lambda: FakePlannerAgent(),
    )
    state = {
        "requirement_doc": {
            "summary": "构建任意业务系统",
            "modules": ["核心流程"],
            "constraints": [],
        },
        "architecture_plan": {
            "architecture_style": "模块化单体",
            "backend": ["Python"],
            "frontend": ["Vue"],
            "modules": [],
        },
        "review_report": {
            "issues": [
                "【关键功能缺失】任务清单中缺少回调安全验证机制任务，存在安全风险。"
            ],
            "suggestions": [
                "【补充任务】新增任务：外部接口异常处理与降级方案，优先级=高，owner=后端。"
            ],
        },
        "review_rounds": 1,
    }

    result = planner_node(state)
    titles = [item["title"] for item in result["task_breakdown"]]
    assert "回调安全验证机制任务" in titles
    assert "外部接口异常处理与降级方案任务" in titles


def test_planner_infers_priority_and_owner_from_review_text(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.planner.build_planner_agent",
        lambda: FakePlannerAgent(),
    )
    state = {
        "requirement_doc": {"summary": "任意系统", "modules": [], "constraints": []},
        "architecture_plan": {
            "architecture_style": "模块化单体",
            "backend": ["Python"],
            "frontend": ["Vue"],
            "modules": [],
        },
        "review_report": {
            "suggestions": [
                "新增任务：统一审计编排，优先级=高，owner=测试工程师。"
            ]
        },
        "review_rounds": 1,
    }

    result = planner_node(state)
    matched = next(
        (t for t in result["task_breakdown"] if t["title"] == "统一审计编排任务"),
        None,
    )
    assert matched is not None
    assert matched["priority"] == "P0"
    assert matched["owner_role"] == "测试工程师"


def test_prompt_builder_aligns_and_fills(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.prompt_builder.build_prompt_builder_agent",
        lambda: FakePromptBuilderAgent(),
    )
    state = {
        "task_breakdown": [
            {
                "title": "任务A",
                "description": "描述A",
                "priority": "P0",
                "depends_on": [],
                "owner_role": "后端",
            },
            {
                "title": "任务B",
                "description": "描述B",
                "priority": "P1",
                "depends_on": ["任务A"],
                "owner_role": "前端",
            },
        ],
        "review_report": {},
        "review_rounds": 0,
    }

    result = prompt_builder_node(state)
    prompt_pack = result["prompt_pack"]
    assert len(prompt_pack) == 2
    assert prompt_pack[0]["task_title"] == "任务A"
    assert prompt_pack[1]["task_title"] == "任务B"
    assert prompt_pack[1]["coding_prompt"]
    assert prompt_pack[1]["test_prompt"]


def test_reviewer_gate_blocks_when_blocking_issue_not_covered(monkeypatch):
    fake = FakeReviewerAgent(passed=True)
    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: fake,
    )
    state = {
        "requirement_doc": {"summary": "test", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {"title": "通用初始化任务", "description": "desc", "priority": "P1", "depends_on": []}
        ],
        "prompt_pack": [{"task_title": "通用初始化任务", "coding_prompt": "a", "test_prompt": "b"}],
        "review_report": {
            "passed": False,
            "issues": ["【关键功能缺失】任务清单中缺少支付回调安全验证机制任务，存在风险。"],
            "suggestions": [],
        },
        "review_rounds": 1,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["next_step"] == "finish"
    assert result["review_rounds"] == 2
    assert result["review_report"]["passed"] is False
    assert fake.calls == 0


def test_reviewer_calls_llm_when_blocking_issue_is_covered(monkeypatch):
    fake = FakeReviewerAgent(passed=True)
    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: fake,
    )
    state = {
        "requirement_doc": {"summary": "test", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {
                "title": "支付回调安全验证机制任务",
                "description": "补齐回调安全验证",
                "priority": "P0",
                "depends_on": [],
            }
        ],
        "prompt_pack": [{"task_title": "支付回调安全验证机制任务", "coding_prompt": "a", "test_prompt": "b"}],
        "review_report": {
            "passed": False,
            "issues": ["【关键功能缺失】任务清单中缺少支付回调安全验证机制任务，存在风险。"],
            "suggestions": [],
        },
        "review_rounds": 1,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["next_step"] == "finish"
    assert result["review_report"]["passed"] is True
    assert fake.calls == 1
