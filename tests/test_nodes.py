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
