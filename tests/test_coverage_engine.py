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
