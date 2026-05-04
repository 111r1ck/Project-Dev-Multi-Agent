import re

from app.agents.schemas import (
    ArchitecturePlan,
    PlannerOutput,
    PromptPackOutput,
    PromptTask,
    RequirementDoc,
    ReviewReport,
    TaskItem,
)
from app.graph.nodes.architect import _normalize_architecture_plan, architect_node
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


class FakeArchitectAgent:
    def invoke(self, _payload):
        return {
            "structured_response": ArchitecturePlan(
                architecture_style="标准前后端分离的模块化单体 (Client-Side Only SPA)",
                backend=[],
                frontend=["React", "IndexedDB"],
                modules=[
                    {
                        "name": "日志审计模块",
                        "responsibility": "记录关键操作日志并支持审计回溯。",
                        "tasks": ["设计日志表结构"],
                    }
                ],
                data_entities=["OperationLog"],
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


def test_architect_normalizes_client_side_style_and_module_responsibilities(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.architect.build_architect_agent",
        lambda: FakeArchitectAgent(),
    )
    state = {
        "requirement_doc": {
            "summary": "开发个人知识库Web，支持本地JSON导入导出与日志记录。",
            "roles": ["个人用户"],
            "modules": ["笔记", "复习", "日志"],
            "constraints": ["本地数据导入导出"],
        },
        "feasibility_report": {
            "feasible": True,
            "complexity": "M",
            "risks": [],
            "mvp_scope": [],
        },
    }

    result = architect_node(state)
    plan = result["architecture_plan"]

    assert "前后端分离" not in plan["architecture_style"]
    assert "Client-Side Only SPA" in plan["architecture_style"]
    assert plan["modules"][0]["responsibilities"] == ["记录关键操作日志并支持审计回溯。"]
    assert "responsibility" not in plan["modules"][0]


def test_architect_normalizes_competing_backend_language_options():
    plan = _normalize_architecture_plan(
        {
            "architecture_style": "标准前后端分离的模块化单体",
            "backend": [
                "Python (FastAPI/Flask)",
                "Java (Spring Boot)",
                "Go (for high concurrency ingestion if needed)",
                "Flink/Spark Streaming",
                "Kafka",
            ],
            "frontend": ["React"],
            "modules": [],
            "data_entities": [],
        }
    )

    assert plan["backend"] == ["Python (FastAPI/Flask)", "Flink/Spark Streaming", "Kafka"]


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


def test_planner_adds_hard_requirement_guardrail_tasks(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.planner.build_planner_agent",
        lambda: FakePlannerAgent(),
    )
    state = {
        "requirement_doc": {
            "summary": "仓储库存管理Web，支持商品入库出库、库存查询、本地JSON导入导出与关键操作日志。",
            "modules": ["库存管理", "查询筛选", "导入导出", "日志"],
            "constraints": [
                "10万条库存流水规模下查询响应时间不超过1秒",
                "入库、出库、盘点调整均有可追踪日志记录",
                "本地数据导入导出JSON",
            ],
        },
        "architecture_plan": {
            "architecture_style": "本地优先的模块化前端单体架构 (Client-Side Only SPA)",
            "backend": [],
            "frontend": ["IndexedDB", "FlexSearch"],
            "modules": [
                {
                    "name": "日志审计模块",
                    "responsibilities": ["记录关键操作日志", "支持导出回溯"],
                }
            ],
        },
        "review_report": {},
        "review_rounds": 0,
        "project_decisions": {},
    }

    result = planner_node(state)
    titles = [item["title"] for item in result["task_breakdown"]]
    guardrail_text = " ".join(
        f"{item.get('title', '')} {item.get('description', '')}"
        for item in result["task_breakdown"]
        if item.get("title") != "基础项目初始化"
    )

    assert "设计核心数据模型与持久化方案" in titles
    assert "建立关键路径延迟基准与性能回归检测" in titles
    assert "完善权限隔离、审计与合规控制" in titles
    assert "笔记" not in guardrail_text
    assert "标签" not in guardrail_text
    assert "复习" not in guardrail_text


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


def test_planner_extracts_supplemental_tasks_from_review_suggestions(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.planner.build_planner_agent",
        lambda: FakePlannerAgent(),
    )
    state = {
        "requirement_doc": {
            "summary": "通用协作平台",
            "modules": ["流程", "内容", "文件"],
            "constraints": [],
        },
        "architecture_plan": {
            "architecture_style": "模块化单体",
            "backend": ["Python"],
            "frontend": ["Vue"],
            "modules": [],
        },
        "review_report": {
            "suggestions": [
                "【补充文件管理任务】任务摘要中未见'文件管理模块实现'任务，建议补充文件上传/下载/删除的完整实现任务。",
                "【补充内容检索任务】需求明确要求内容推荐，建议补充内容检索与推荐任务。",
                "【补充登录集成任务】建议补充本地账号登录、双登录方式切换逻辑的实现任务。",
            ],
        },
        "review_rounds": 1,
    }

    result = planner_node(state)
    titles = [item["title"] for item in result["task_breakdown"]]

    assert "文件上传/下载/删除的完整实现任务" in titles
    assert "内容检索与推荐任务" in titles
    assert "本地账号登录、双登录方式切换逻辑的实现任务" in titles


def test_planner_extracts_missing_feature_tasks_from_blocking_issues(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.planner.build_planner_agent",
        lambda: FakePlannerAgent(),
    )
    state = {
        "requirement_doc": {
            "summary": "会议室预订系统",
            "modules": ["预订", "用户中心"],
            "constraints": [],
        },
        "architecture_plan": {
            "architecture_style": "模块化单体",
            "backend": ["Python"],
            "frontend": ["Vue"],
            "modules": [],
        },
        "review_report": {
            "passed": False,
            "issues": [
                "回流覆盖检查未通过：以下关键阻塞项尚未被任务清单命中。",
                "功能缺失：需求明确要求'取消预订'功能，但任务列表中无对应实现任务，属于硬性需求缺失",
                "功能缺失：需求明确要求'查看个人预订记录'功能，但任务列表中无对应实现任务，属于硬性需求缺失",
            ],
            "suggestions": [
                "请先补齐上述阻塞项对应任务，再进入评审。"
            ],
        },
        "review_rounds": 1,
    }

    result = planner_node(state)
    titles = [item["title"] for item in result["task_breakdown"]]

    assert "取消预订任务" in titles
    assert "查看个人预订记录任务" in titles


def test_planner_appends_review_time_constraints_to_existing_task(monkeypatch):
    class CompliancePlannerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": PlannerOutput(
                    tasks=[
                        TaskItem(
                            title="外部审批材料准备与跟踪",
                            description="完成外部审批材料准备。",
                            priority="P1",
                            depends_on=[],
                            owner_role="产品经理",
                        )
                    ]
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.planner.build_planner_agent",
        lambda: CompliancePlannerAgent(),
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
                "【明确合规时间节点】在'外部审批材料准备与跟踪'任务中添加时间约束：'上线前2周启动材料提交，上线前1周完成审核与验证'。"
            ]
        },
        "review_rounds": 1,
    }

    result = planner_node(state)
    compliance_task = next(
        task for task in result["task_breakdown"] if task["title"] == "外部审批材料准备与跟踪"
    )

    assert "上线前2周启动材料提交" in compliance_task["description"]
    assert "上线前1周完成审核与验证" in compliance_task["description"]


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


def test_planner_adds_resource_protection_task_for_resource_exhaustion_risk(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.planner.build_planner_agent",
        lambda: FakePlannerAgent(),
    )
    state = {
        "requirement_doc": {
            "summary": "通用平台，支持数据导出与报表能力",
            "modules": ["报表"],
            "constraints": [],
        },
        "feasibility_report": {
            "feasible": True,
            "complexity": "H",
            "risks": ["大数据量导出场景存在内存溢出与资源耗尽风险"],
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
    assert "实现大结果集处理与资源保护机制" in titles


def test_planner_does_not_add_resource_protection_task_when_already_covered(monkeypatch):
    class CoveredPlannerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": PlannerOutput(
                    tasks=[
                        TaskItem(
                            title="实现流式导出与异步任务处理",
                            description="采用流式写入、分页分片与异步队列处理大结果集，控制内存水位。",
                            priority="P0",
                            depends_on=[],
                            owner_role="后端开发工程师",
                        )
                    ]
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.planner.build_planner_agent",
        lambda: CoveredPlannerAgent(),
    )
    state = {
        "requirement_doc": {"summary": "任意系统", "modules": [], "constraints": []},
        "feasibility_report": {
            "feasible": True,
            "complexity": "H",
            "risks": ["批量导出时可能出现OOM"],
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
    assert titles.count("实现大结果集处理与资源保护机制") == 0


def test_planner_adds_concurrency_guardrail_task_from_risk(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.planner.build_planner_agent",
        lambda: FakePlannerAgent(),
    )
    state = {
        "requirement_doc": {"summary": "预约系统", "modules": [], "constraints": []},
        "feasibility_report": {
            "feasible": True,
            "complexity": "M",
            "risks": ["并发预订冲突需依靠数据库唯一索引或事务锁保证一致性"],
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
    assert "设计并发冲突防护与唯一约束策略" in titles


def test_prompt_builder_aligns_and_fills(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.prompt_builder.build_prompt_builder_agent",
        lambda: FakePromptBuilderAgent(),
    )
    monkeypatch.setattr(
        "app.graph.nodes.prompt_builder.load_cached_prompts",
        lambda _project_id, _review_rounds, tasks: ([None] * len(tasks), list(range(len(tasks)))),
    )
    monkeypatch.setattr(
        "app.graph.nodes.prompt_builder.save_cached_prompts",
        lambda *_args, **_kwargs: None,
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
    assert prompt_pack[1]["is_fallback"] is True


def test_prompt_builder_generates_missing_tasks_in_batches(monkeypatch):
    calls = []

    class BatchPromptBuilderAgent:
        def invoke(self, payload):
            content = payload["messages"][0]["content"]
            calls.append(content)
            titles = re.findall(r"^- (.+?) \| priority=", content, flags=re.MULTILINE)
            return {
                "structured_response": PromptPackOutput(
                    prompts=[
                        PromptTask(
                            task_title=title,
                            coding_prompt=f"实现{title}",
                            test_prompt=f"测试{title}",
                        )
                        for title in titles
                    ]
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.prompt_builder.build_prompt_builder_agent",
        lambda: BatchPromptBuilderAgent(),
    )
    monkeypatch.setattr(
        "app.graph.nodes.prompt_builder.load_cached_prompts",
        lambda _project_id, _review_rounds, tasks: ([None] * len(tasks), list(range(len(tasks)))),
    )
    monkeypatch.setattr(
        "app.graph.nodes.prompt_builder.save_cached_prompts",
        lambda *_args, **_kwargs: None,
    )
    tasks = [
        {
            "title": f"任务{i}",
            "description": f"描述{i}",
            "priority": "P1",
            "depends_on": [],
            "owner_role": "后端开发工程师",
        }
        for i in range(10)
    ]

    result = prompt_builder_node(
        {
            "task_breakdown": tasks,
            "review_report": {},
            "review_rounds": 0,
        }
    )

    assert len(calls) == 2
    assert len(result["prompt_pack"]) == 10
    assert all(not item.get("is_fallback") for item in result["prompt_pack"])


def test_prompt_builder_forces_non_fallback_for_p0_after_retries(monkeypatch):
    class AlwaysMismatchedPromptAgent:
        def __init__(self):
            self.calls = 0

        def invoke(self, _payload):
            self.calls += 1
            return {
                "structured_response": PromptPackOutput(
                    prompts=[
                        PromptTask(
                            task_title="不匹配任务标题",
                            coding_prompt="cp",
                            test_prompt="tp",
                        )
                    ]
                )
            }

    fake = AlwaysMismatchedPromptAgent()
    monkeypatch.setattr(
        "app.graph.nodes.prompt_builder.build_prompt_builder_agent",
        lambda: fake,
    )
    monkeypatch.setattr(
        "app.graph.nodes.prompt_builder.load_cached_prompts",
        lambda _project_id, _review_rounds, tasks: ([None] * len(tasks), list(range(len(tasks)))),
    )
    monkeypatch.setattr(
        "app.graph.nodes.prompt_builder.save_cached_prompts",
        lambda *_args, **_kwargs: None,
    )

    state = {
        "task_breakdown": [
            {
                "title": "P0关键任务",
                "description": "关键链路",
                "priority": "P0",
                "depends_on": [],
                "owner_role": "后端开发工程师",
            },
            {
                "title": "普通任务",
                "description": "普通链路",
                "priority": "P2",
                "depends_on": [],
                "owner_role": "后端开发工程师",
            },
        ],
        "review_report": {},
        "review_rounds": 0,
    }

    result = prompt_builder_node(state)
    prompt_pack = result["prompt_pack"]
    p0_prompt = prompt_pack[0]
    p2_prompt = prompt_pack[1]

    assert fake.calls >= 2
    assert p0_prompt["task_title"] == "P0关键任务"
    assert p0_prompt.get("is_fallback") is False
    assert p0_prompt.get("forced_for_p0") is True
    assert "输入：" in p0_prompt["coding_prompt"]
    assert "回归测试" in p0_prompt["test_prompt"]
    assert p2_prompt.get("is_fallback") is True


def test_prompt_builder_budget_guard_truncates_and_fills_fallback(monkeypatch):
    calls = []

    class BudgetedPromptBuilderAgent:
        def invoke(self, payload):
            content = payload["messages"][0]["content"]
            calls.append(content)
            titles = re.findall(r"^- (.+?) \| priority=", content, flags=re.MULTILINE)
            return {
                "structured_response": PromptPackOutput(
                    prompts=[
                        PromptTask(
                            task_title=title,
                            coding_prompt=f"实现{title}",
                            test_prompt=f"测试{title}",
                        )
                        for title in titles
                    ]
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.prompt_builder.PROMPT_BUILD_MAX_MODEL_CALLS",
        1,
    )
    monkeypatch.setattr(
        "app.graph.nodes.prompt_builder.build_prompt_builder_agent",
        lambda: BudgetedPromptBuilderAgent(),
    )
    monkeypatch.setattr(
        "app.graph.nodes.prompt_builder.load_cached_prompts",
        lambda _project_id, _review_rounds, tasks: ([None] * len(tasks), list(range(len(tasks)))),
    )
    monkeypatch.setattr(
        "app.graph.nodes.prompt_builder.save_cached_prompts",
        lambda *_args, **_kwargs: None,
    )

    tasks = [
        {
            "title": f"任务{i}",
            "description": f"描述{i}",
            "priority": "P1",
            "depends_on": [],
            "owner_role": "后端开发工程师",
        }
        for i in range(10)
    ]

    result = prompt_builder_node(
        {
            "task_breakdown": tasks,
            "review_report": {},
            "review_rounds": 0,
        }
    )

    assert len(calls) == 1
    diagnostics = result.get("prompt_builder_diagnostics", {})
    assert diagnostics.get("truncated") is True
    assert "max_model_calls" in (diagnostics.get("truncated_reasons") or [])
    assert len(result["prompt_pack"]) == 10
    assert any(bool(item.get("is_fallback")) for item in result["prompt_pack"])


def test_reviewer_gate_blocks_when_blocking_issue_not_covered(monkeypatch):
    fake = FakeReviewerAgent(passed=True)
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
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
    assert isinstance(result["review_report"].get("diagnostics", []), list)
    assert result["review_report"]["diagnostics"]
    assert fake.calls == 0


def test_reviewer_allows_conditional_pass_when_round_limit_reached_with_coverage_only_issues(monkeypatch):
    fake = FakeReviewerAgent(passed=True)
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: fake,
    )
    state = {
        "requirement_doc": {"summary": "test", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {"title": "验证关键假设与替代方案", "description": "验证假设", "priority": "P0", "depends_on": []},
            {"title": "落实受控假设的风险控制措施", "description": "风险控制", "priority": "P0", "depends_on": []},
        ],
        "prompt_pack": [
            {"task_title": "验证关键假设与替代方案", "coding_prompt": "a", "test_prompt": "b"},
            {"task_title": "落实受控假设的风险控制措施", "coding_prompt": "a", "test_prompt": "b"},
        ],
        "assumption_pack": {
            "human_gate_exhausted": True,
            "blocking": [],
            "prelaunch_checklist": [{"item": "外部依赖SLA确认", "phase": "上线前确认", "status": "pending"}],
            "requires_user_confirmation": [{"item": "外部依赖SLA确认", "phase": "上线前确认"}],
        },
        "review_report": {
            "passed": False,
            "issues": [
                "回流覆盖检查未通过：以下关键阻塞项尚未被任务清单命中。",
                "建议在任务标题中显式包含阻塞项关键词，并补充依赖关系与验收标准。",
            ],
            "suggestions": [],
        },
        "review_rounds": 1,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["next_step"] == "finish"
    assert result["review_report"]["passed"] is True
    assert result["review_report"]["passed_with_conditions"] is True
    assert result["review_report"]["conditions"][0]["item"] == "外部依赖SLA确认"
    assert fake.calls == 0


def test_reviewer_calls_llm_when_blocking_issue_is_covered(monkeypatch):
    fake = FakeReviewerAgent(passed=True)
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
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


def test_reviewer_calls_llm_when_quoted_feature_issue_is_covered(monkeypatch):
    fake = FakeReviewerAgent(passed=True)
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: fake,
    )
    state = {
        "requirement_doc": {"summary": "会议室预订", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {
                "title": "开发取消预订接口（后端）",
                "description": "提供取消预订接口并校验权限。",
                "priority": "P0",
                "depends_on": [],
            },
            {
                "title": "开发小程序取消预订功能",
                "description": "在预订记录页面实现取消预订入口与确认流程。",
                "priority": "P0",
                "depends_on": ["开发取消预订接口（后端）"],
            },
        ],
        "prompt_pack": [
            {"task_title": "开发取消预订接口（后端）", "coding_prompt": "a", "test_prompt": "b"},
            {"task_title": "开发小程序取消预订功能", "coding_prompt": "a", "test_prompt": "b"},
        ],
        "review_report": {
            "passed": False,
            "issues": [
                "功能缺失：需求明确要求'取消预订'功能，但任务列表中未见取消预订相关任务（后端接口+前端页面），属于硬性需求遗漏"
            ],
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


def test_reviewer_calls_llm_when_timeout_strategy_issue_is_covered(monkeypatch):
    fake = FakeReviewerAgent(passed=True)
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: fake,
    )
    state = {
        "requirement_doc": {"summary": "会议室预订", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {
                "title": "审批超时自动处理任务",
                "description": "实现定时任务扫描审批超时记录，自动取消并释放会议室资源，记录日志并通知相关人。",
                "priority": "P0",
                "depends_on": ["审批流状态机设计与实现"],
            }
        ],
        "prompt_pack": [
            {"task_title": "审批超时自动处理任务", "coding_prompt": "a", "test_prompt": "b"},
        ],
        "review_report": {
            "passed": False,
            "issues": [
                "【审批超时策略未定义】风险中提到'缺乏明确的超时自动策略会导致会议室资源长期锁定'，但任务列表中未见'审批超时自动处理'相关任务（如定时任务、超时释放逻辑），这将导致高优先级会议室资源被待审批状态长期占用。"
            ],
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


def test_reviewer_gate_downgrades_low_confidence_issue_instead_of_blocking(monkeypatch):
    fake = FakeReviewerAgent(passed=True)
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: fake,
    )
    state = {
        "requirement_doc": {"summary": "会议室预订", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {
                "title": "开发预订流程",
                "description": "实现预订链路",
                "priority": "P1",
                "depends_on": [],
            }
        ],
        "prompt_pack": [{"task_title": "开发预订流程", "coding_prompt": "a", "test_prompt": "b"}],
        "review_report": {
            "passed": False,
            "issues": ["体验问题：建议优化页面操作体验，减少点击步骤。"],
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


def test_reviewer_gate_accepts_semantic_coverage_for_data_retention(monkeypatch):
    fake = FakeReviewerAgent(passed=True)
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: fake,
    )
    state = {
        "requirement_doc": {"summary": "test", "constraints": ["关键数据保留不少于2年"]},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {
                "title": "定义数据生命周期管理策略",
                "description": "制定关键数据2年保留、冷热分层、归档、容量预估和恢复验证。",
                "priority": "P0",
                "depends_on": [],
            }
        ],
        "prompt_pack": [{"task_title": "定义数据生命周期管理策略", "coding_prompt": "a", "test_prompt": "b"}],
        "review_report": {
            "passed": False,
            "issues": ["【数据保留策略缺失】需求要求关键数据保留≥2年，但无数据生命周期管理、归档策略、存储容量规划相关任务"],
            "suggestions": [],
        },
        "review_rounds": 1,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)

    assert result["review_report"]["passed"] is True
    assert fake.calls == 1


def test_reviewer_gate_accepts_semantic_coverage_for_concurrency_constraints(monkeypatch):
    fake = FakeReviewerAgent(passed=True)
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: fake,
    )
    state = {
        "requirement_doc": {"summary": "预约平台", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {
                "title": "设计并发冲突防护与唯一约束策略",
                "description": "为会议室ID+日期+时段建立组合唯一索引，并结合事务锁与幂等校验处理并发冲突。",
                "priority": "P0",
                "depends_on": [],
            }
        ],
        "prompt_pack": [{"task_title": "设计并发冲突防护与唯一约束策略", "coding_prompt": "a", "test_prompt": "b"}],
        "review_report": {
            "passed": False,
            "issues": [
                "【并发控制方案不完整】并发预订冲突需依靠数据库唯一索引或事务锁，但任务列表未体现唯一索引设计。"
            ],
            "suggestions": [],
        },
        "review_rounds": 1,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)

    assert result["review_report"]["passed"] is True
    assert fake.calls == 1


def test_reviewer_blocks_p0_fallback_prompts(monkeypatch):
    fake = FakeReviewerAgent(passed=True)
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
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
                "title": "建立关键路径延迟基准与性能回归检测",
                "description": "定义延迟基准。",
                "priority": "P0",
                "depends_on": [],
            }
        ],
        "prompt_pack": [
            {
                "task_title": "建立关键路径延迟基准与性能回归检测",
                "coding_prompt": "fallback",
                "test_prompt": "fallback",
                "is_fallback": True,
            }
        ],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)

    assert result["next_step"] == "prompt_builder"
    assert result["review_rounds"] == 1
    assert result["review_report"]["passed"] is False
    assert "P0任务使用了兜底提示词" in result["review_report"]["issues"][0]
    assert fake.calls == 0


def test_reviewer_forces_rework_when_passed_report_contains_blocking_issues(monkeypatch):
    class ContradictoryReviewerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": ReviewReport(
                    passed=True,
                    issues=[
                        "性能验证方案缺失：任务缺少1万条数据的测试数据集准备与性能基准测试用例。",
                        "纯前端架构的日志持久化风险：需明确日志是否需要导出为JSON。",
                    ],
                    suggestions=["补充性能测试用例"],
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: ContradictoryReviewerAgent(),
    )
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    state = {
        "requirement_doc": {
            "summary": "个人知识库Web",
            "constraints": ["1万条笔记搜索响应时间不超过1秒"],
        },
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "Client-Side Only SPA", "backend": [], "frontend": []},
        "task_breakdown": [
            {"title": "开发全文检索功能", "description": "desc", "priority": "P1", "depends_on": []}
        ],
        "prompt_pack": [{"task_title": "开发全文检索功能", "coding_prompt": "a", "test_prompt": "b"}],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)

    assert result["next_step"] == "planner"
    assert result["review_rounds"] == 1
    assert result["review_report"]["passed"] is False


def test_reviewer_postprocess_downgrades_contradictory_issue_to_suggestion(monkeypatch):
    class ContradictoryCoverageReviewerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": ReviewReport(
                    passed=False,
                    issues=[
                        "【硬性需求缺失-签到方案】需求明确要求'开始后未取消且未签到记1次违规'，但签到采集方式未确定。"
                    ],
                    suggestions=[
                        "【签到方案决策】建议MVP采用手动签到+二维码签到双模式。"
                    ],
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: ContradictoryCoverageReviewerAgent(),
    )
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    state = {
        "requirement_doc": {"summary": "会议室预订", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {
                "title": "设计签到技术方案",
                "description": "确定手动签到+二维码签到双模式，并给出签到状态流转与GPS校验逻辑。",
                "priority": "P0",
                "depends_on": [],
            }
        ],
        "prompt_pack": [
            {
                "task_title": "设计签到技术方案",
                "coding_prompt": "实现手动签到+二维码签到并明确状态机。",
                "test_prompt": "覆盖签到路径与异常场景。",
            }
        ],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["next_step"] == "finish"
    assert result["review_report"]["passed"] is True
    assert result["review_report"]["issues"] == []
    assert any("已降级为建议" in item for item in result["review_report"]["suggestions"])


def test_reviewer_postprocess_downgrades_missing_claim_when_task_exists(monkeypatch):
    class ContradictoryMissingClaimReviewerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": ReviewReport(
                    passed=False,
                    issues=[
                        "【关键功能缺失】需求明确要求'部门维度报表导出'，但任务列表中未发现报表开发相关任务，核心功能缺失将导致无法验收",
                        "【审计合规风险】需求要求'敏感操作日志需保留至少6个月'，但任务列表中未发现操作日志审计模块的开发任务，存在合规性风险",
                    ],
                    suggestions=[],
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: ContradictoryMissingClaimReviewerAgent(),
    )
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    state = {
        "requirement_doc": {"summary": "企业固定资产借用与盘点系统", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {
                "title": "前端报表中心页面开发",
                "description": "开发报表中心页面，展示部门维度资产统计数据并实现报表导出功能。",
                "priority": "P0",
                "depends_on": [],
            },
            {
                "title": "实现部门维度报表与导出功能",
                "description": "开发按部门维度统计并提供Excel报表导出能力。",
                "priority": "P0",
                "depends_on": [],
            },
            {
                "title": "实现操作日志审计模块",
                "description": "记录关键业务操作并确保日志数据保留至少6个月。",
                "priority": "P0",
                "depends_on": [],
            },
        ],
        "prompt_pack": [
            {
                "task_title": "实现部门维度报表与导出功能",
                "coding_prompt": "实现部门维度报表查询和导出。",
                "test_prompt": "覆盖导出与筛选路径。",
            },
            {
                "task_title": "实现操作日志审计模块",
                "coding_prompt": "实现审计日志记录和保留策略。",
                "test_prompt": "覆盖日志留存与归档场景。",
            },
        ],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["next_step"] == "finish"
    assert result["review_report"]["passed"] is True
    assert result["review_report"]["issues"] == []
    assert len(result["review_report"]["suggestions"]) >= 1
    diagnostics = result["review_report"].get("diagnostics", [])
    matched = [
        item
        for item in diagnostics
        if isinstance(item, dict)
        and "部门维度报表导出" in str(item.get("issue_text", ""))
    ]
    assert matched
    assert any(
        str(item.get("final_disposition", "")) in {"downgraded_to_suggestion", "dropped_as_covered"}
        for item in matched
    )


def test_reviewer_postprocess_downgrades_cycle_issue_when_graph_has_no_cycle(monkeypatch):
    class CycleClaimReviewerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": ReviewReport(
                    passed=False,
                    issues=[
                        "【循环依赖阻塞】任务1与任务2存在循环依赖：任务1依赖任务2，任务2又依赖任务1，导致无法确定实施顺序",
                    ],
                    suggestions=[],
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: CycleClaimReviewerAgent(),
    )
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    state = {
        "requirement_doc": {"summary": "固定资产系统", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {"title": "任务1", "description": "基础建模", "priority": "P0", "depends_on": []},
            {"title": "任务2", "description": "后端框架", "priority": "P0", "depends_on": ["任务1"]},
        ],
        "prompt_pack": [{"task_title": "任务2", "coding_prompt": "a", "test_prompt": "b"}],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["next_step"] == "finish"
    assert result["review_report"]["passed"] is True
    assert result["review_report"]["issues"] == []
    assert any("已降级为建议" in item for item in result["review_report"]["suggestions"])


def test_reviewer_postprocess_keeps_cycle_issue_when_graph_has_cycle(monkeypatch):
    class CycleClaimReviewerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": ReviewReport(
                    passed=False,
                    issues=[
                        "【循环依赖阻塞】任务A与任务B存在循环依赖，需要先重构依赖关系。",
                    ],
                    suggestions=[],
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: CycleClaimReviewerAgent(),
    )
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    state = {
        "requirement_doc": {"summary": "固定资产系统", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {"title": "任务A", "description": "A", "priority": "P0", "depends_on": ["任务B"]},
            {"title": "任务B", "description": "B", "priority": "P0", "depends_on": ["任务A"]},
        ],
        "prompt_pack": [],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["next_step"] == "planner"
    assert result["review_report"]["passed"] is False
    assert result["review_report"]["issues"]


def test_reviewer_postprocess_downgrades_research_timing_dispute(monkeypatch):
    class TimingDisputeReviewerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": ReviewReport(
                    passed=False,
                    issues=[
                        "二维码扫描兼容性验证时机错误：'验证移动端二维码扫描兼容性'被标记为P0优先级且deps=0，但实际依赖'实现二维码生成与绑定功能'才能验证。"
                    ],
                    suggestions=[],
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: TimingDisputeReviewerAgent(),
    )
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    state = {
        "requirement_doc": {"summary": "固定资产系统", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {
                "title": "验证移动端二维码扫描兼容性",
                "description": "【技术预研】验证iOS/Android主流浏览器扫码权限与兼容性，输出选型建议。",
                "priority": "P0",
                "depends_on": [],
            },
            {
                "title": "实现二维码生成与绑定功能",
                "description": "实现二维码生成、绑定与解析。",
                "priority": "P0",
                "depends_on": [],
            },
        ],
        "prompt_pack": [],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["next_step"] == "finish"
    assert result["review_report"]["passed"] is True
    assert result["review_report"]["issues"] == []
    assert any("已降级为建议" in item for item in result["review_report"]["suggestions"])


def test_reviewer_consistency_guard_restores_blocking_uncovered(monkeypatch):
    class BlockingIssueReviewerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": ReviewReport(
                    passed=False,
                    issues=["【关键功能缺失】缺少核心对账校验任务。"],
                    suggestions=[],
                )
            }

    def fake_coverage(_tasks, issues, **_kwargs):
        return {
            "uncovered": [],
            "downgraded": list(issues),
            "diagnostics": [
                {
                    "issue_text": "【关键功能缺失】缺少核心对账校验任务。",
                    "decision": "blocking_uncovered",
                    "is_blocking": True,
                }
            ],
        }

    monkeypatch.setattr("app.graph.nodes.reviewer.analyze_blocking_issue_coverage", fake_coverage)
    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: BlockingIssueReviewerAgent(),
    )
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    state = {
        "requirement_doc": {"summary": "demo", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [{"title": "基础任务", "description": "desc", "priority": "P1", "depends_on": []}],
        "prompt_pack": [],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["next_step"] == "planner"
    assert result["review_report"]["passed"] is False
    assert "【关键功能缺失】缺少核心对账校验任务。" in result["review_report"]["issues"]
    diags = result["review_report"].get("diagnostics", [])
    matched = [
        item
        for item in diags
        if isinstance(item, dict)
        and item.get("issue_text") == "【关键功能缺失】缺少核心对账校验任务。"
    ]
    assert matched
    assert any(str(item.get("final_disposition", "")) == "kept_blocking" for item in matched)
    assert any("postprocess_reason_code" in item for item in matched)


def test_reviewer_downgrades_performance_data_sufficiency_issue(monkeypatch):
    class PerfIssueReviewerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": ReviewReport(
                    passed=False,
                    issues=[
                        "【性能验证-阻塞】全文检索性能基准测试缺少真实数据支撑，当前依赖关系无法保证性能测试有效性。"
                    ],
                    suggestions=[],
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: PerfIssueReviewerAgent(),
    )
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    state = {
        "requirement_doc": {"summary": "检索系统", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {
                "title": "全文检索索引优化与性能基准测试",
                "description": "使用30万合同样本数据集，验证P95<=800ms、P99<=1500ms并输出QPS基线。",
                "priority": "P0",
                "depends_on": [],
            }
        ],
        "prompt_pack": [],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["next_step"] == "finish"
    assert result["review_report"]["passed"] is True
    assert result["review_report"]["issues"] == []
    assert any("已降级为建议" in item for item in result["review_report"]["suggestions"])
    diags = result["review_report"].get("diagnostics", [])
    matched = [
        item
        for item in diags
        if isinstance(item, dict)
        and "性能基准测试缺少真实数据支撑" in str(item.get("issue_text", ""))
    ]
    assert matched
    assert any(str(item.get("final_disposition", "")) == "downgraded_to_suggestion" for item in matched)
    tiers = result["review_report"].get("suggestion_tiers", [])
    assert isinstance(tiers, list)
    assert all(isinstance(item, dict) and "tier" in item and "text" in item for item in tiers)


def test_reviewer_keeps_dependency_timing_blocking_when_foundation_reverse_dependency(monkeypatch):
    class TimingIssueReviewerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": ReviewReport(
                    passed=False,
                    issues=[
                        "dependency timing issue: 'design and initialize database schema' depends on 'frontend-backend integration test', which is reversed and blocks execution"
                    ],
                    suggestions=[],
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: TimingIssueReviewerAgent(),
    )
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    state = {
        "requirement_doc": {"summary": "demo", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {
                "title": "Frontend and backend integration test",
                "description": "End-to-end integration validation.",
                "priority": "P0",
                "depends_on": [],
            },
            {
                "title": "Design and initialize database schema",
                "description": "Define schema and create DDL.",
                "priority": "P0",
                "depends_on": ["Frontend and backend integration test"],
            },
        ],
        "prompt_pack": [],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["review_report"]["passed"] is False
    assert result["review_report"]["issues"]
    diagnostics = result["review_report"].get("diagnostics", [])
    matched = [
        item
        for item in diagnostics
        if isinstance(item, dict)
        and "dependency timing issue" in str(item.get("issue_text", ""))
    ]
    assert matched
    assert any(str(item.get("final_disposition", "")) == "kept_blocking" for item in matched)


def test_reviewer_keeps_dependency_timing_blocking_when_build_depends_on_finalization(monkeypatch):
    class TimingIssueReviewerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": ReviewReport(
                    passed=False,
                    issues=[
                        "dependency timing issue: build task depends on production deployment, execution order is reversed"
                    ],
                    suggestions=[],
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: TimingIssueReviewerAgent(),
    )
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    state = {
        "requirement_doc": {"summary": "demo", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {
                "title": "生产环境部署与上线",
                "description": "执行生产发布、切流与上线验收。",
                "priority": "P0",
                "depends_on": [],
            },
            {
                "title": "合同全生命周期管理模块开发",
                "description": "实现合同创建、审批、签署、归档流程。",
                "priority": "P0",
                "depends_on": ["生产环境部署与上线"],
            },
        ],
        "prompt_pack": [],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["review_report"]["passed"] is False
    assert result["review_report"]["issues"]
    diagnostics = result["review_report"].get("diagnostics", [])
    matched = [
        item
        for item in diagnostics
        if isinstance(item, dict)
        and "build task depends on production deployment" in str(item.get("issue_text", ""))
    ]
    assert matched
    assert any(str(item.get("final_disposition", "")) == "kept_blocking" for item in matched)


def test_reviewer_keeps_dependency_timing_blocking_when_backend_depends_on_frontend_scaffold(monkeypatch):
    class TimingIssueReviewerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": ReviewReport(
                    passed=False,
                    issues=[
                        "architecture conflict: backend process task depends on frontend scaffold"
                    ],
                    suggestions=[],
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: TimingIssueReviewerAgent(),
    )
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    state = {
        "requirement_doc": {"summary": "demo", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [
            {
                "title": "搭建前端框架与路由配置",
                "description": "初始化前端应用与路由。",
                "priority": "P0",
                "depends_on": [],
            },
            {
                "title": "后端流程引擎集成与配置",
                "description": "集成后端流程能力并实现业务流程。",
                "priority": "P0",
                "depends_on": ["搭建前端框架与路由配置"],
            },
        ],
        "prompt_pack": [],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["review_report"]["passed"] is False
    assert result["review_report"]["issues"]
    diagnostics = result["review_report"].get("diagnostics", [])
    matched = [
        item
        for item in diagnostics
        if isinstance(item, dict)
        and "backend process task depends on frontend scaffold" in str(item.get("issue_text", ""))
    ]
    assert matched
    assert any(str(item.get("final_disposition", "")) == "kept_blocking" for item in matched)


def test_reviewer_downgrades_architecture_conflict_without_hard_microservice_evidence(monkeypatch):
    class ArchConflictReviewerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": ReviewReport(
                    passed=False,
                    issues=[
                        "【架构冲突】架构风格标注为模块化单体，但任务拆解看起来像微服务拆分。"
                    ],
                    suggestions=[],
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: ArchConflictReviewerAgent(),
    )
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    state = {
        "requirement_doc": {"summary": "demo", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "模块化单体 + 前后端分离", "backend": [], "frontend": []},
        "task_breakdown": [
            {
                "title": "后端模块化单体框架搭建",
                "description": "定义模块边界与依赖关系。",
                "priority": "P0",
                "depends_on": [],
            },
            {
                "title": "后端公共组件开发",
                "description": "开发统一异常处理与组件能力。",
                "priority": "P0",
                "depends_on": ["后端模块化单体框架搭建"],
            },
        ],
        "prompt_pack": [],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["review_report"]["passed"] is True
    assert result["review_report"]["issues"] == []
    diagnostics = result["review_report"].get("diagnostics", [])
    matched = [
        item
        for item in diagnostics
        if isinstance(item, dict)
        and "架构冲突" in str(item.get("issue_text", ""))
    ]
    assert matched
    assert any(str(item.get("final_disposition", "")) == "downgraded_to_suggestion" for item in matched)


def test_reviewer_keeps_blocking_for_data_boundary_conflict_missing_implementation(monkeypatch):
    class DataBoundaryConflictReviewerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": ReviewReport(
                    passed=False,
                    issues=["【架构冲突】多租户与数据主权要求未见隔离实现任务。"],
                    suggestions=[],
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: DataBoundaryConflictReviewerAgent(),
    )
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    state = {
        "requirement_doc": {"summary": "demo", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "模块化单体", "backend": [], "frontend": []},
        "task_breakdown": [
            {"title": "后端框架搭建", "description": "初始化后端工程", "priority": "P0", "depends_on": []},
            {"title": "订单模块开发", "description": "实现订单CRUD", "priority": "P0", "depends_on": []},
        ],
        "prompt_pack": [],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["review_report"]["passed"] is False
    assert result["review_report"]["issues"]
    diagnostics = result["review_report"].get("diagnostics", [])
    matched = [
        item
        for item in diagnostics
        if isinstance(item, dict)
        and "多租户与数据主权要求未见隔离实现任务" in str(item.get("issue_text", ""))
    ]
    assert matched
    assert any(str(item.get("final_disposition", "")) == "kept_blocking" for item in matched)


def test_reviewer_keeps_blocking_for_sync_async_mismatch_conflict(monkeypatch):
    class SyncAsyncConflictReviewerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": ReviewReport(
                    passed=False,
                    issues=["【架构冲突】需要异步事件驱动链路，但当前任务仅定义同步直连接口。"],
                    suggestions=[],
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: SyncAsyncConflictReviewerAgent(),
    )
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    state = {
        "requirement_doc": {"summary": "demo", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "模块化单体", "backend": [], "frontend": []},
        "task_breakdown": [
            {"title": "审批同步接口开发", "description": "基于request-response直连处理审批链路", "priority": "P0", "depends_on": []},
            {"title": "预算同步校验接口", "description": "同步实时接口校验预算", "priority": "P0", "depends_on": []},
        ],
        "prompt_pack": [],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["review_report"]["passed"] is False
    assert result["review_report"]["issues"]
    diagnostics = result["review_report"].get("diagnostics", [])
    matched = [
        item
        for item in diagnostics
        if isinstance(item, dict)
        and "需要异步事件驱动链路" in str(item.get("issue_text", ""))
    ]
    assert matched
    assert any(str(item.get("final_disposition", "")) == "kept_blocking" for item in matched)


def test_reviewer_keeps_blocking_for_state_model_conflict_missing_implementation(monkeypatch):
    class StateModelConflictReviewerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": ReviewReport(
                    passed=False,
                    issues=["【架构冲突】状态机与幂等控制要求未落地，当前仅直接更新状态字段。"],
                    suggestions=[],
                )
            }

    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: StateModelConflictReviewerAgent(),
    )
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)
    state = {
        "requirement_doc": {"summary": "demo", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "模块化单体", "backend": [], "frontend": []},
        "task_breakdown": [
            {"title": "订单状态直接更新接口", "description": "直接更新订单状态并同步写入，不加锁", "priority": "P0", "depends_on": []},
            {"title": "审批结果直接覆盖", "description": "直接覆盖审批状态字段", "priority": "P0", "depends_on": []},
        ],
        "prompt_pack": [],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    result = reviewer_node(state)
    assert result["review_report"]["passed"] is False
    assert result["review_report"]["issues"]
    diagnostics = result["review_report"].get("diagnostics", [])
    matched = [
        item
        for item in diagnostics
        if isinstance(item, dict)
        and "状态机与幂等控制要求未落地" in str(item.get("issue_text", ""))
    ]
    assert matched
    assert any(str(item.get("final_disposition", "")) == "kept_blocking" for item in matched)


def test_reviewer_node_persists_term_cluster_memory_across_runs(monkeypatch):
    class MemoryLearningReviewerAgent:
        def invoke(self, _payload):
            return {
                "structured_response": ReviewReport(
                    passed=False,
                    issues=["Missing security compliance validation task"],
                    suggestions=[],
                )
            }

    call_inputs: list[dict] = []

    def fake_coverage(tasks, issues, **kwargs):
        incoming_memory = dict(kwargs.get("term_cluster_memory", {}) or {})
        call_inputs.append(incoming_memory)
        co = dict(incoming_memory.get("cooccurrence", {}) or {})
        key = "security||compliance"
        co[key] = int(co.get(key, 0)) + 1
        return {
            "uncovered": [],
            "downgraded": list(issues),
            "diagnostics": [
                {
                    "issue_text": "Missing security compliance validation task",
                    "decision": "downgraded_uncovered",
                    "is_blocking": False,
                }
            ],
            "term_cluster_memory": {"cooccurrence": co},
            "learned_clusters": {},
        }

    monkeypatch.setattr("app.graph.nodes.reviewer.analyze_blocking_issue_coverage", fake_coverage)
    monkeypatch.setattr(
        "app.graph.nodes.reviewer.build_reviewer_agent",
        lambda: MemoryLearningReviewerAgent(),
    )
    monkeypatch.setattr("app.graph.nodes.reviewer.load_cached_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.graph.nodes.reviewer.save_cached_review", lambda *_args, **_kwargs: None)

    base_state = {
        "project_id": "memory-e2e-project",
        "requirement_doc": {"summary": "demo", "constraints": []},
        "feasibility_report": {"feasible": True, "complexity": "M", "risks": []},
        "architecture_plan": {"architecture_style": "mono", "backend": [], "frontend": []},
        "task_breakdown": [{"title": "Security task", "description": "Implement audit and compliance checks", "priority": "P0", "depends_on": []}],
        "prompt_pack": [],
        "review_report": {},
        "review_rounds": 0,
        "max_review_rounds": 2,
        "errors": [],
    }

    first = reviewer_node(base_state)
    first_memory = dict(first.get("term_cluster_memory", {}) or {})
    assert isinstance(first_memory.get("cooccurrence", {}), dict)
    assert int(first_memory.get("cooccurrence", {}).get("security||compliance", 0)) == 1

    second = reviewer_node(first)
    second_memory = dict(second.get("term_cluster_memory", {}) or {})
    assert int(second_memory.get("cooccurrence", {}).get("security||compliance", 0)) > int(
        first_memory.get("cooccurrence", {}).get("security||compliance", 0)
    )
    assert len(call_inputs) >= 2
    assert call_inputs[0] == {}
    assert int(call_inputs[1].get("cooccurrence", {}).get("security||compliance", 0)) == 1
