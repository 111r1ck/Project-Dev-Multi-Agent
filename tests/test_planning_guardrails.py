from app.services.constraint_classifier import ConstraintSignal
from app.services.planning_guardrails import (
    align_dependency_priorities,
    ensure_architecture_module_tasks,
    ensure_guardrail_tasks,
)
from app.services.task_dependency_resolver import resolve_task_dependencies


def test_guardrail_tasks_are_generated_from_generic_constraint_categories():
    tasks = [
        {
            "title": "实现核心业务接口",
            "description": "实现核心写操作。",
            "priority": "P0",
            "depends_on": [],
            "owner_role": "后端",
        }
    ]
    signals = [
        ConstraintSignal(category="capacity", evidence=["容量要求"], sources=["requirement_doc"]),
        ConstraintSignal(category="observability", evidence=["监控要求"], sources=["project_decisions"]),
        ConstraintSignal(category="release_safety", evidence=["发布要求"], sources=["project_decisions"]),
    ]

    result = ensure_guardrail_tasks(tasks, signals)
    titles = {item["title"] for item in result}
    combined_text = " ".join(f"{item['title']} {item['description']}" for item in result)

    assert "建立容量模型与负载基准测试" in titles
    assert "建立指标采集、告警与日志追踪体系" in titles
    assert "制定灰度发布、回滚与变更验证机制" in titles
    assert "商品" not in combined_text
    assert "订单" not in combined_text
    assert "笔记" not in combined_text


def test_dependency_resolver_adds_foundational_dependencies_without_cycles():
    tasks = [
        {
            "title": "设计核心数据模型与持久化方案",
            "description": "定义实体关系与持久化结构。",
            "priority": "P0",
            "depends_on": [],
            "owner_role": "架构师",
        },
        {
            "title": "实现认证权限与访问控制",
            "description": "保护管理接口。",
            "priority": "P0",
            "depends_on": [],
            "owner_role": "后端",
        },
        {
            "title": "实现核心业务接口",
            "description": "实现受保护的关键写操作。",
            "priority": "P0",
            "depends_on": [],
            "owner_role": "后端",
        },
        {
            "title": "建立容量模型与负载基准测试",
            "description": "验证关键路径容量。",
            "priority": "P0",
            "depends_on": [],
            "owner_role": "测试",
        },
    ]

    result = resolve_task_dependencies(tasks)
    by_title = {item["title"]: item for item in result}

    assert "设计核心数据模型与持久化方案" in by_title["实现核心业务接口"]["depends_on"]
    assert "实现认证权限与访问控制" in by_title["实现核心业务接口"]["depends_on"]
    assert "实现核心业务接口" in by_title["建立容量模型与负载基准测试"]["depends_on"]
    for item in result:
        assert item["title"] not in item["depends_on"]


def test_architecture_modules_without_tasks_get_generic_implementation_tasks():
    tasks = [
        {
            "title": "实现核心业务接口",
            "description": "实现核心流程。",
            "priority": "P0",
            "depends_on": [],
            "owner_role": "后端开发工程师",
        }
    ]
    architecture_plan = {
        "modules": [
            {
                "name": "文件处理模块",
                "responsibilities": ["负责文件上传、下载、删除和存储清理。"],
            },
            {
                "name": "内容检索模块",
                "responsibilities": ["负责内容索引、搜索和推荐。"],
            },
        ]
    }

    result = ensure_architecture_module_tasks(tasks, architecture_plan)
    titles = {item["title"] for item in result}

    assert "实现文件处理模块核心功能" in titles
    assert "实现内容检索模块核心功能" in titles


def test_dependency_priority_is_promoted_when_high_priority_task_depends_on_lower_priority_task():
    tasks = [
        {
            "title": "基础能力实现",
            "description": "提供核心前置能力。",
            "priority": "P2",
            "depends_on": [],
            "owner_role": "后端开发工程师",
        },
        {
            "title": "关键业务流程实现",
            "description": "实现关键业务流程。",
            "priority": "P0",
            "depends_on": ["基础能力实现"],
            "owner_role": "后端开发工程师",
        },
    ]

    result = align_dependency_priorities(tasks)
    by_title = {item["title"]: item for item in result}

    assert by_title["基础能力实现"]["priority"] == "P0"
