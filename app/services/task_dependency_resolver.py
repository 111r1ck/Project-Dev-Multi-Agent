from __future__ import annotations

from app.graph.nodes.common import detect_dependency_cycles


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(marker.lower() in normalized for marker in markers)


def _task_text(task: dict) -> str:
    return f"{task.get('title', '')} {task.get('description', '')}"


def normalize_owner_role(owner_role: str) -> str:
    normalized = str(owner_role or "").strip()
    aliases = {
        "后端": "后端开发工程师",
        "后端工程师": "后端开发工程师",
        "后端开发": "后端开发工程师",
        "前端": "前端开发工程师",
        "前端工程师": "前端开发工程师",
        "前端开发": "前端开发工程师",
        "测试": "测试工程师",
        "测试人员": "测试工程师",
        "qa": "测试工程师",
        "QA": "测试工程师",
        "运维": "DevOps工程师",
        "运维工程师": "DevOps工程师",
        "devops": "DevOps工程师",
        "DevOps": "DevOps工程师",
        "DevOps工程师": "DevOps工程师",
        "开发": "后端开发工程师",
    }
    return aliases.get(normalized, normalized or "后端开发工程师")


def _find_first(tasks: list[dict], markers: tuple[str, ...], exclude_title: str = "") -> str | None:
    for task in tasks:
        title = str(task.get("title", "")).strip()
        if title == exclude_title:
            continue
        if _contains_any(_task_text(task), markers):
            return title or None
    return None


def _is_runtime_resilience_task(task: dict) -> bool:
    text = _task_text(task)
    return _contains_any(
        text,
        ("限流", "降级", "熔断", "故障演练", "运行时保障", "容灾演练", "重试补偿"),
    )


def _find_first_non_resilience(tasks: list[dict], markers: tuple[str, ...]) -> str | None:
    for task in tasks:
        if _is_runtime_resilience_task(task):
            continue
        title = str(task.get("title", "")).strip()
        if _contains_any(_task_text(task), markers):
            return title or None
    return None


def _find_notification_service(tasks: list[dict]) -> str | None:
    for task in tasks:
        text = _task_text(task)
        if _contains_any(text, ("到期", "超时", "提醒", "告警触发", "事件触发")):
            continue
        title = str(task.get("title", "")).strip()
        if _contains_any(text, ("通知", "消息", "投递", "推送", "webhook", "Webhook", "外部通道", "消息通道")):
            return title or None
    return None


def _append_dep(task: dict, dep: str | None, titles: set[str]) -> None:
    if not dep or dep == task.get("title") or dep not in titles:
        return
    deps = [str(item) for item in (task.get("depends_on", []) or [])]
    if dep not in deps:
        deps.append(dep)
    task["depends_on"] = deps


def _remove_unknown_and_self_dependencies(task: dict, titles: set[str]) -> None:
    title = str(task.get("title", "")).strip()
    cleaned: list[str] = []
    for dep in task.get("depends_on", []) or []:
        dep_title = str(dep).strip()
        if dep_title and dep_title != title and dep_title in titles and dep_title not in cleaned:
            cleaned.append(dep_title)
    task["depends_on"] = cleaned


def resolve_task_dependencies(tasks: list[dict]) -> list[dict]:
    resolved = [dict(task) for task in tasks]
    for task in resolved:
        task["owner_role"] = normalize_owner_role(str(task.get("owner_role", "")))

    titles = {str(task.get("title", "")).strip() for task in resolved if task.get("title")}

    data_model = _find_first(resolved, ("数据模型", "持久化", "schema", "表结构", "数据结构"))
    auth_access = _find_first(resolved, ("认证", "权限", "访问控制", "隔离", "上下文", "rbac"))
    consistency = _find_first_non_resilience(resolved, ("幂等", "状态机", "补偿", "一致性"))
    observability = _find_first(resolved, ("监控", "告警", "日志追踪", "指标采集"))
    core_business = _find_first(resolved, ("核心业务", "核心接口", "关键路径", "关键写操作"))
    notification = _find_notification_service(resolved)
    event_source = _find_first(
        resolved,
        ("事件生成", "生成告警", "告警事件", "异常检测", "事件发布", "消息发布"),
    )

    for task in resolved:
        title = str(task.get("title", "")).strip()
        text = _task_text(task)

        if _contains_any(text, ("业务", "接口", "写操作", "查询", "管理", "流程", "创建", "记录", "存储")):
            _append_dep(task, data_model, titles)

        if _contains_any(text, ("自动创建", "自动派发", "触发", "接收告警", "监听事件", "下游流程")):
            _append_dep(task, event_source, titles)

        if _contains_any(text, ("受保护", "接口", "管理", "操作", "权限", "隔离")):
            _append_dep(task, auth_access, titles)

        if _contains_any(text, ("关键写操作", "回调", "重试", "补偿", "状态", "重复")):
            _append_dep(task, consistency, titles)

        if _contains_any(text, ("到期", "超时", "提醒", "告警触发", "事件触发")):
            _append_dep(task, notification, titles)

        if _contains_any(text, ("容量", "负载", "性能", "延迟", "压测", "基准")):
            _append_dep(task, core_business, titles)

        if _contains_any(text, ("发布", "回滚", "灰度", "变更")):
            _append_dep(task, observability, titles)

        _remove_unknown_and_self_dependencies(task, titles)
        if title and "depends_on" not in task:
            task["depends_on"] = []

    return resolved


def break_dependency_cycles(tasks: list[dict]) -> tuple[list[dict], dict]:
    """
    Remove dependency edges heuristically until task graph becomes acyclic.
    Returns (fixed_tasks, diagnostics).
    """
    fixed = [dict(task) for task in tasks]
    by_title = {
        str(task.get("title", "")).strip(): task
        for task in fixed
        if str(task.get("title", "")).strip()
    }
    removed_edges: list[dict[str, str]] = []

    def _task_text_by_title(title: str) -> str:
        task = by_title.get(title, {})
        return f"{task.get('title', '')} {task.get('description', '')}"

    def _is_validation_or_integration(title: str) -> bool:
        text = _task_text_by_title(title)
        return _contains_any(text, ("测试", "压测", "集成", "验收", "验证", "回归"))

    def _is_foundation_or_scaffold(title: str) -> bool:
        text = _task_text_by_title(title)
        return _contains_any(text, ("脚手架", "初始化", "基础配置", "schema", "表结构", "数据库"))

    def _is_core_implementation(title: str) -> bool:
        text = _task_text_by_title(title)
        return _contains_any(text, ("实现", "引擎", "核心", "crud", "流程"))

    def _edge_rank(src: str, dep: str) -> tuple[int, int, int, int]:
        # lower rank => remove first
        src_validation = 0 if _is_validation_or_integration(src) else 1
        dep_validation = 0 if _is_validation_or_integration(dep) else 1
        src_foundation = 0 if _is_foundation_or_scaffold(src) else 1
        dep_core = 0 if _is_core_implementation(dep) else 1
        return (src_validation, dep_validation, src_foundation, dep_core)

    before = detect_dependency_cycles(fixed)
    guard = 0
    while True:
        analysis = detect_dependency_cycles(fixed)
        cycles = analysis.get("cycles", []) or []
        if not cycles:
            break
        guard += 1
        if guard > 50:
            break

        chosen_src = ""
        chosen_dep = ""
        chosen_rank = (9, 9, 9, 9)
        for cycle in cycles:
            nodes = [str(n).strip() for n in cycle if str(n).strip()]
            if len(nodes) < 2:
                continue
            for i in range(len(nodes) - 1):
                src = nodes[i]
                dep = nodes[i + 1]
                rank = _edge_rank(src, dep)
                if rank < chosen_rank:
                    chosen_rank = rank
                    chosen_src = src
                    chosen_dep = dep
        if not chosen_src or not chosen_dep:
            break

        src_task = by_title.get(chosen_src)
        if not src_task:
            break
        deps = [str(item).strip() for item in (src_task.get("depends_on", []) or []) if str(item).strip()]
        new_deps = [item for item in deps if item != chosen_dep]
        if len(new_deps) == len(deps):
            break
        src_task["depends_on"] = new_deps
        removed_edges.append({"from": chosen_src, "to": chosen_dep})

    after = detect_dependency_cycles(fixed)
    diagnostics = {
        "had_cycles_before": bool(before.get("has_cycle")),
        "cycles_before": (before.get("cycles", []) or [])[:5],
        "cycles_after": (after.get("cycles", []) or [])[:5],
        "has_cycle_after": bool(after.get("has_cycle")),
        "removed_edges": removed_edges,
    }
    return fixed, diagnostics


def fix_dependency_direction_anti_patterns(tasks: list[dict]) -> tuple[list[dict], dict]:
    """
    Fix common direction anti-patterns in dependencies.
    Generic rule:
    - Foundation tasks (schema/infra/bootstrap/model) must not depend on
      integration/testing/validation/UAT tasks.
    """
    fixed = [dict(task) for task in tasks]
    by_title = {
        str(task.get("title", "")).strip(): task
        for task in fixed
        if str(task.get("title", "")).strip()
    }
    rewired: list[dict[str, str]] = []

    def _task_text(task: dict) -> str:
        return f"{task.get('title', '')} {task.get('description', '')}"

    def _is_foundation(task: dict) -> bool:
        text = _task_text(task)
        return _contains_any(
            text,
            (
                "schema",
                "表结构",
                "数据库",
                "ddl",
                "数据模型",
                "初始化",
                "基础设施",
                "脚手架",
                "infra",
                "bootstrap",
                "data model",
                "database",
            ),
        )

    def _is_validation_or_integration(task: dict) -> bool:
        text = _task_text(task)
        return _contains_any(
            text,
            (
                "联调",
                "集成",
                "测试",
                "压测",
                "验收",
                "验证",
                "回归",
                "integration",
                "e2e",
                "uat",
                "test",
                "testing",
                "validation",
                "benchmark",
            ),
        )

    for task in fixed:
        title = str(task.get("title", "")).strip()
        if not title:
            continue
        if not _is_foundation(task):
            continue
        deps = [str(dep).strip() for dep in (task.get("depends_on", []) or []) if str(dep).strip()]
        new_deps: list[str] = []
        for dep in deps:
            dep_task = by_title.get(dep)
            if dep_task and _is_validation_or_integration(dep_task):
                rewired.append({"from": title, "removed_dep": dep, "reason": "foundation_depends_on_validation"})
                continue
            if dep not in new_deps:
                new_deps.append(dep)
        task["depends_on"] = new_deps

    return fixed, {"direction_fixes": rewired}
