from app.graph.nodes.common import analyze_blocking_issue_coverage, detect_dependency_cycles


def test_coverage_engine_marks_issue_as_covered_with_multi_source_evidence():
    tasks = [
        {
            "title": "开发取消预订接口（后端）",
            "description": "实现取消预订接口并完成权限校验。",
            "depends_on": [],
        },
        {
            "title": "开发小程序取消预订功能",
            "description": "前端页面联调取消预订接口。",
            "depends_on": ["开发取消预订接口（后端）"],
        },
    ]
    prompts = [
        {
            "task_title": "开发取消预订接口（后端）",
            "coding_prompt": "实现取消预订业务逻辑与错误处理。",
            "test_prompt": "覆盖取消预订正常/异常流。",
        }
    ]
    issues = [
        "功能缺失：需求明确要求'取消预订'功能，但任务列表中未见取消预订相关任务（后端接口+前端页面）"
    ]

    result = analyze_blocking_issue_coverage(
        tasks,
        issues,
        prompt_pack=prompts,
        min_evidence_hits=2,
        min_confidence=0.65,
        blocking_confidence=0.75,
    )
    assert result["uncovered"] == []
    assert result["downgraded"] == []
    assert result["diagnostics"][0]["decision"] == "covered"


def test_coverage_engine_blocks_high_confidence_missing_issue():
    tasks = [
        {"title": "基础项目初始化", "description": "初始化项目", "depends_on": []},
    ]
    issues = ["【关键功能缺失】任务清单中缺少支付回调安全验证机制任务，存在风险。"]

    result = analyze_blocking_issue_coverage(
        tasks,
        issues,
        prompt_pack=[],
        min_evidence_hits=2,
        min_confidence=0.65,
        blocking_confidence=0.75,
    )
    assert result["uncovered"] == issues
    assert result["diagnostics"][0]["is_blocking"] is True


def test_coverage_engine_downgrades_low_confidence_issue():
    tasks = [
        {"title": "开发预订流程", "description": "实现预订流程", "depends_on": []},
    ]
    issues = ["体验问题：建议优化页面操作体验，减少点击步骤。"]

    result = analyze_blocking_issue_coverage(
        tasks,
        issues,
        prompt_pack=[],
        min_evidence_hits=2,
        min_confidence=0.65,
        blocking_confidence=0.75,
    )
    assert result["uncovered"] == []
    assert result["downgraded"] == issues
    assert result["diagnostics"][0]["decision"] == "downgraded_uncovered"


def test_detect_dependency_cycles_finds_cycle():
    tasks = [
        {"title": "任务A", "description": "", "depends_on": ["任务B"]},
        {"title": "任务B", "description": "", "depends_on": ["任务A"]},
    ]
    result = detect_dependency_cycles(tasks)
    assert result["has_cycle"] is True
    assert result["cycles"]


def test_detect_dependency_cycles_handles_acyclic_graph():
    tasks = [
        {"title": "任务1", "description": "", "depends_on": []},
        {"title": "任务2", "description": "", "depends_on": ["任务1"]},
    ]
    result = detect_dependency_cycles(tasks)
    assert result["has_cycle"] is False
    assert result["cycles"] == []


def test_coverage_engine_weak_match_recovery_marks_as_covered():
    tasks = [
        {
            "title": "实现附件归档策略与定时清理任务",
            "description": "附件默认保留5年，超期自动归档，定时任务每日执行并记录日志。",
            "depends_on": [],
        }
    ]
    prompts = [
        {
            "task_title": "实现附件归档策略与定时清理任务",
            "coding_prompt": "实现归档策略和定时清理机制。",
            "test_prompt": "覆盖5年保留与超期归档场景。",
        }
    ]
    issues = [
        "【关键需求遗漏】需求明确要求'附件默认保留5年，超期自动归档'，但任务列表中未见附件管理、归档策略、定时清理相关任务，合规性功能缺失"
    ]

    result = analyze_blocking_issue_coverage(
        tasks,
        issues,
        prompt_pack=prompts,
        min_evidence_hits=2,
        min_confidence=0.65,
        blocking_confidence=0.75,
    )
    assert result["uncovered"] == []
    assert result["diagnostics"][0]["decision"] == "covered"


def test_coverage_engine_compound_security_terms_mark_as_covered():
    tasks = [
        {
            "title": "实现安全审计与访问日志留存",
            "description": "实现数据脱敏、访问日志记录与安全审计检查。",
            "depends_on": [],
        }
    ]
    prompts = [
        {
            "task_title": "实现安全审计与访问日志留存",
            "coding_prompt": "实现访问日志与脱敏处理。",
            "test_prompt": "覆盖审计与合规验证场景。",
        }
    ]
    issues = [
        "缺少安全合规验证任务：关键约束要求数据符合公司信息安全规范，但未发现安全审计、数据脱敏、访问日志等合规验证任务"
    ]

    result = analyze_blocking_issue_coverage(
        tasks,
        issues,
        prompt_pack=prompts,
        min_evidence_hits=2,
        min_confidence=0.65,
        blocking_confidence=0.75,
    )
    assert result["uncovered"] == []
    assert result["diagnostics"][0]["decision"] == "covered"


def test_coverage_engine_english_missing_claim_marks_as_covered():
    tasks = [
        {
            "title": "Implement security compliance validation tasks",
            "description": "Add security audit checks, data masking, and access log validation.",
            "depends_on": [],
        }
    ]
    prompts = [
        {
            "task_title": "Implement security compliance validation tasks",
            "coding_prompt": "Implement audit log and data masking controls.",
            "test_prompt": "Cover security audit and compliance validation scenarios.",
        }
    ]
    issues = [
        "Missing security compliance validation task: requirement explicitly requires data to meet security policies, but no security audit, data masking, or access log validation tasks were found"
    ]

    result = analyze_blocking_issue_coverage(
        tasks,
        issues,
        prompt_pack=prompts,
        min_evidence_hits=2,
        min_confidence=0.65,
        blocking_confidence=0.75,
    )
    assert result["uncovered"] == []
    assert result["diagnostics"][0]["decision"] == "covered"


def test_coverage_engine_term_cluster_memory_grows_and_supports_second_round():
    tasks_round1 = [
        {
            "title": "Implement security audit and access log retention",
            "description": "Add compliance checks, access log recording, and security audit verification.",
            "depends_on": [],
        }
    ]
    prompts_round1 = [
        {
            "task_title": "Implement security audit and access log retention",
            "coding_prompt": "Implement audit log and compliance controls.",
            "test_prompt": "Cover security audit and access log compliance scenarios.",
        }
    ]
    issues_round1 = [
        "Missing security compliance validation task: requirement requires security audit and access log controls"
    ]

    first = analyze_blocking_issue_coverage(
        tasks_round1,
        issues_round1,
        prompt_pack=prompts_round1,
        min_evidence_hits=2,
        min_confidence=0.65,
        blocking_confidence=0.75,
        term_cluster_memory={},
    )
    memory_after_first = first.get("term_cluster_memory", {})
    assert isinstance(memory_after_first, dict)
    assert isinstance(memory_after_first.get("cooccurrence", {}), dict)
    assert len(memory_after_first.get("cooccurrence", {})) >= 1

    tasks_round2 = [
        {
            "title": "Build compliance validation pipeline",
            "description": "Validate audit and access logs for security controls.",
            "depends_on": [],
        }
    ]
    prompts_round2 = [
        {
            "task_title": "Build compliance validation pipeline",
            "coding_prompt": "Implement security compliance checks for audit/access logs.",
            "test_prompt": "Verify compliance validation behavior.",
        }
    ]
    issues_round2 = [
        "Missing security audit access log validation tasks"
    ]

    second = analyze_blocking_issue_coverage(
        tasks_round2,
        issues_round2,
        prompt_pack=prompts_round2,
        min_evidence_hits=2,
        min_confidence=0.65,
        blocking_confidence=0.75,
        term_cluster_memory=memory_after_first,
    )
    memory_after_second = second.get("term_cluster_memory", {})
    co_first = memory_after_first.get("cooccurrence", {})
    co_second = memory_after_second.get("cooccurrence", {})
    assert isinstance(co_second, dict)
    assert len(co_second) >= len(co_first)
    assert isinstance(second.get("learned_clusters", {}), dict)
    # second round should not regress into hard uncovered in this aligned scenario
    assert second["uncovered"] == []
