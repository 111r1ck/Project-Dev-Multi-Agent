from pathlib import Path

from app.services.task_dependency_resolver import break_dependency_cycles, resolve_task_dependencies


def test_resolver_links_alert_work_order_to_alert_generation():
    tasks = [
        {
            "title": "设计核心数据模型与持久化方案",
            "description": "定义告警、工单和设备数据模型。",
            "priority": "P0",
            "depends_on": [],
            "owner_role": "数据工程师",
        },
        {
            "title": "设计并实现异常检测模型推理逻辑",
            "description": "消费实时数据并生成告警事件。",
            "priority": "P0",
            "depends_on": [],
            "owner_role": "后端",
        },
        {
            "title": "自动创建维修工单",
            "description": "接收告警事件并自动创建工单，完成派发和升级。",
            "priority": "P0",
            "depends_on": [],
            "owner_role": "后端开发工程师",
        },
    ]

    resolved = resolve_task_dependencies(tasks)
    work_order = next(task for task in resolved if task["title"] == "自动创建维修工单")

    assert "设计核心数据模型与持久化方案" in work_order["depends_on"]
    assert "设计并实现异常检测模型推理逻辑" in work_order["depends_on"]


def test_resolver_normalizes_owner_roles():
    tasks = [
        {
            "title": "后端任务",
            "description": "实现接口。",
            "priority": "P1",
            "depends_on": [],
            "owner_role": "后端",
        },
        {
            "title": "运维任务",
            "description": "配置监控。",
            "priority": "P1",
            "depends_on": [],
            "owner_role": "运维工程师",
        },
    ]

    resolved = resolve_task_dependencies(tasks)
    roles = {task["title"]: task["owner_role"] for task in resolved}

    assert roles["后端任务"] == "后端开发工程师"
    assert roles["运维任务"] == "DevOps工程师"


def test_resolver_does_not_block_core_business_on_runtime_resilience():
    tasks = [
        {
            "title": "设计核心数据模型与持久化方案",
            "description": "定义用户、工单、评论、附件和操作日志表结构。",
            "priority": "P0",
            "depends_on": [],
            "owner_role": "数据工程师",
        },
        {
            "title": "限流降级、重试补偿与故障演练方案",
            "description": "设计运行期限流、熔断、降级和故障演练。",
            "priority": "中",
            "depends_on": [],
            "owner_role": "运维",
        },
        {
            "title": "工单创建及状态流转功能",
            "description": "实现工单提交、分配、优先级、状态流转和评论协作。",
            "priority": "最高",
            "depends_on": [],
            "owner_role": "后端",
        },
        {
            "title": "集成外部身份提供方登录流程",
            "description": "实现第三方SSO登录并绑定本地用户。",
            "priority": "高",
            "depends_on": [],
            "owner_role": "后端",
        },
    ]

    resolved = resolve_task_dependencies(tasks)
    by_title = {task["title"]: task for task in resolved}

    assert "设计核心数据模型与持久化方案" in by_title["工单创建及状态流转功能"]["depends_on"]
    assert "限流降级、重试补偿与故障演练方案" not in by_title["工单创建及状态流转功能"]["depends_on"]
    assert "限流降级、重试补偿与故障演练方案" not in by_title["集成外部身份提供方登录流程"]["depends_on"]


def test_resolver_links_due_reminder_engine_to_message_delivery_service():
    tasks = [
        {
            "title": "到期提醒引擎",
            "description": "根据规则触发到期、超时和异常提醒。",
            "priority": "P0",
            "depends_on": [],
            "owner_role": "后端",
        },
        {
            "title": "消息投递服务集成",
            "description": "集成消息通道、推送网关和外部Webhook。",
            "priority": "P1",
            "depends_on": [],
            "owner_role": "后端",
        },
    ]

    resolved = resolve_task_dependencies(tasks)
    reminder_task = next(task for task in resolved if task["title"] == "到期提醒引擎")

    assert "消息投递服务集成" in reminder_task["depends_on"]


def test_dependency_resolver_has_no_single_scenario_channel_markers():
    source = Path("app/services/task_dependency_resolver.py").read_text(encoding="utf-8")
    scenario_markers = ("\u4f01\u5fae", "\u7ad9\u5185\u4fe1")

    assert all(marker not in source for marker in scenario_markers)


def test_break_dependency_cycles_removes_cycle_edges():
    tasks = [
        {
            "title": "集成MinIO对象存储服务",
            "description": "部署对象存储并提供上传下载能力。",
            "priority": "P0",
            "depends_on": ["集成测试与性能压测"],
            "owner_role": "后端",
        },
        {
            "title": "集成测试与性能压测",
            "description": "执行集成测试与压测。",
            "priority": "P0",
            "depends_on": ["存量合同数据迁移"],
            "owner_role": "测试",
        },
        {
            "title": "存量合同数据迁移",
            "description": "迁移历史数据并验证完整性。",
            "priority": "P0",
            "depends_on": ["集成MinIO对象存储服务"],
            "owner_role": "后端",
        },
    ]

    fixed, diagnostics = break_dependency_cycles(tasks)
    assert diagnostics["had_cycles_before"] is True
    assert diagnostics["has_cycle_after"] is False
    assert diagnostics["removed_edges"]
    by_title = {item["title"]: item for item in fixed}
    assert "集成测试与性能压测" not in by_title["集成MinIO对象存储服务"]["depends_on"]
