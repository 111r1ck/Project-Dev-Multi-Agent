from app.services.architecture_conflict_checker import check_architecture_conflict


def test_checker_downgrades_singleton_vs_microservice_without_hard_evidence():
    result = check_architecture_conflict(
        issue_text="【架构冲突】模块化单体与任务拆解不一致，疑似微服务化",
        architecture_plan={"architecture_style": "模块化单体 + 前后端分离"},
        tasks=[
            {
                "title": "后端模块化单体框架搭建",
                "description": "定义模块边界与依赖关系",
            },
            {
                "title": "后端公共组件开发",
                "description": "实现公共组件与拦截器",
            },
        ],
    )
    assert result["is_architecture_conflict_issue"] is True
    assert result["conflict_type"] == "singleton_vs_microservice"
    assert result["has_hard_evidence"] is False
    assert result["severity"] == "suggestion"


def test_checker_blocks_singleton_vs_microservice_with_hard_evidence():
    result = check_architecture_conflict(
        issue_text="architecture conflict: monolith plan but service split tasks found",
        architecture_plan={"architecture_style": "modular monolith"},
        tasks=[
            {
                "title": "服务A独立部署",
                "description": "独立部署并通过跨服务调用访问服务B",
            }
        ],
    )
    assert result["is_architecture_conflict_issue"] is True
    assert result["conflict_type"] == "singleton_vs_microservice"
    assert result["has_hard_evidence"] is True
    assert result["severity"] == "blocking"


def test_checker_blocks_backend_depends_on_frontend_scaffold_conflict():
    result = check_architecture_conflict(
        issue_text="architecture conflict: backend process task depends on frontend scaffold",
        architecture_plan={"architecture_style": "模块化单体 + 前后端分离"},
        tasks=[
            {"title": "搭建前端框架与路由配置", "description": "初始化前端应用与路由", "depends_on": []},
            {
                "title": "后端流程引擎集成与配置",
                "description": "实现后端流程能力",
                "depends_on": ["搭建前端框架与路由配置"],
            },
        ],
    )
    assert result["is_architecture_conflict_issue"] is True
    assert result["conflict_type"] == "deployment_model_conflict"
    assert result["has_hard_evidence"] is True
    assert result["severity"] == "blocking"


def test_checker_blocks_data_boundary_conflict_when_implementation_missing():
    result = check_architecture_conflict(
        issue_text="【架构冲突】多租户与数据主权要求未见隔离实现任务",
        architecture_plan={"architecture_style": "模块化单体"},
        tasks=[
            {"title": "后端框架搭建", "description": "初始化后端工程", "depends_on": []},
            {"title": "订单模块开发", "description": "实现订单CRUD", "depends_on": []},
        ],
    )
    assert result["is_architecture_conflict_issue"] is True
    assert result["conflict_type"] == "data_boundary_conflict"
    assert result["has_hard_evidence"] is True
    assert result["severity"] == "blocking"


def test_checker_downgrades_data_boundary_conflict_when_implementation_exists():
    result = check_architecture_conflict(
        issue_text="architecture conflict: tenant isolation not implemented",
        architecture_plan={"architecture_style": "modular monolith"},
        tasks=[
            {"title": "Tenant isolation interceptor", "description": "Implement tenant context and row-level security"},
            {"title": "Data masking and audit", "description": "Add data masking and audit logs"},
        ],
    )
    assert result["is_architecture_conflict_issue"] is True
    assert result["conflict_type"] == "data_boundary_conflict"
    assert result["has_hard_evidence"] is False
    assert result["severity"] == "suggestion"


def test_checker_blocks_sync_async_mismatch_when_only_sync_signals():
    result = check_architecture_conflict(
        issue_text="architecture conflict: async event-driven model required but implementation is synchronous",
        architecture_plan={"architecture_style": "modular monolith"},
        tasks=[
            {"title": "审批同步接口开发", "description": "基于request-response直连处理审批链路"},
            {"title": "预算同步校验接口", "description": "同步实时接口校验预算"},
        ],
    )
    assert result["is_architecture_conflict_issue"] is True
    assert result["conflict_type"] == "sync_vs_async_mismatch"
    assert result["has_hard_evidence"] is True
    assert result["severity"] == "blocking"


def test_checker_downgrades_sync_async_mismatch_when_async_implementation_exists():
    result = check_architecture_conflict(
        issue_text="需要异步事件驱动能力",
        architecture_plan={"architecture_style": "模块化单体"},
        tasks=[
            {"title": "事件发布与消费模块", "description": "实现异步事件发布、消费与重试补偿"},
            {"title": "Outbox可靠消息机制", "description": "落地outbox与消息投递"},
        ],
    )
    assert result["is_architecture_conflict_issue"] is True
    assert result["conflict_type"] == "sync_vs_async_mismatch"
    assert result["has_hard_evidence"] is False
    assert result["severity"] == "suggestion"


def test_checker_blocks_deployment_model_conflict_when_build_depends_on_finalization():
    result = check_architecture_conflict(
        issue_text="【架构冲突】开发任务依赖上线发布，部署模型冲突",
        architecture_plan={"architecture_style": "模块化单体"},
        tasks=[
            {"title": "生产环境部署与上线", "description": "执行发布与切流", "depends_on": []},
            {"title": "核心业务模块开发", "description": "实现核心业务能力", "depends_on": ["生产环境部署与上线"]},
        ],
    )
    assert result["is_architecture_conflict_issue"] is True
    assert result["conflict_type"] == "deployment_model_conflict"
    assert result["has_hard_evidence"] is True
    assert result["severity"] == "blocking"


def test_checker_downgrades_deployment_model_conflict_when_order_is_reasonable():
    result = check_architecture_conflict(
        issue_text="architecture conflict: deployment model unclear",
        architecture_plan={"architecture_style": "modular monolith"},
        tasks=[
            {"title": "核心业务模块开发", "description": "实现核心业务能力", "depends_on": []},
            {"title": "生产环境部署与上线", "description": "执行发布与切流", "depends_on": ["核心业务模块开发"]},
        ],
    )
    assert result["is_architecture_conflict_issue"] is True
    assert result["conflict_type"] == "deployment_model_conflict"
    assert result["has_hard_evidence"] is False
    assert result["severity"] == "suggestion"


def test_checker_blocks_state_model_conflict_when_only_direct_mutation_signals():
    result = check_architecture_conflict(
        issue_text="【架构冲突】状态机与事务一致性要求未落地，当前仅直接更新状态",
        architecture_plan={"architecture_style": "模块化单体"},
        tasks=[
            {"title": "订单状态直接更新接口", "description": "直接更新订单状态并同步写入，不加锁"},
            {"title": "审批结果直接覆盖", "description": "直接覆盖审批状态字段"},
        ],
    )
    assert result["is_architecture_conflict_issue"] is True
    assert result["conflict_type"] == "state_model_conflict"
    assert result["has_hard_evidence"] is True
    assert result["severity"] == "blocking"


def test_checker_downgrades_state_model_conflict_when_state_controls_exist():
    result = check_architecture_conflict(
        issue_text="state machine and idempotency controls required",
        architecture_plan={"architecture_style": "modular monolith"},
        tasks=[
            {"title": "状态机与幂等控制实现", "description": "实现状态流转、幂等校验、事务与补偿策略"},
            {"title": "并发锁与版本号控制", "description": "实现乐观锁版本号与并发冲突处理"},
        ],
    )
    assert result["is_architecture_conflict_issue"] is True
    assert result["conflict_type"] == "state_model_conflict"
    assert result["has_hard_evidence"] is False
    assert result["severity"] == "suggestion"
