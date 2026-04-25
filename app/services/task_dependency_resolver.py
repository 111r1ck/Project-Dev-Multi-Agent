from __future__ import annotations


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(marker.lower() in normalized for marker in markers)


def _task_text(task: dict) -> str:
    return f"{task.get('title', '')} {task.get('description', '')}"


def _find_first(tasks: list[dict], markers: tuple[str, ...], exclude_title: str = "") -> str | None:
    for task in tasks:
        title = str(task.get("title", "")).strip()
        if title == exclude_title:
            continue
        if _contains_any(_task_text(task), markers):
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
    titles = {str(task.get("title", "")).strip() for task in resolved if task.get("title")}

    data_model = _find_first(resolved, ("数据模型", "持久化", "schema", "表结构", "数据结构"))
    auth_access = _find_first(resolved, ("认证", "权限", "访问控制", "隔离", "上下文", "rbac"))
    consistency = _find_first(resolved, ("幂等", "状态机", "补偿", "一致性"))
    observability = _find_first(resolved, ("监控", "告警", "日志追踪", "指标采集"))
    core_business = _find_first(resolved, ("核心业务", "核心接口", "关键路径", "关键写操作"))

    for task in resolved:
        title = str(task.get("title", "")).strip()
        text = _task_text(task)

        if _contains_any(text, ("业务", "接口", "写操作", "查询", "管理", "流程")):
            _append_dep(task, data_model, titles)

        if _contains_any(text, ("受保护", "接口", "管理", "操作", "权限", "隔离")):
            _append_dep(task, auth_access, titles)

        if _contains_any(text, ("关键写操作", "回调", "重试", "补偿", "状态", "重复")):
            _append_dep(task, consistency, titles)

        if _contains_any(text, ("容量", "负载", "性能", "延迟", "压测", "基准")):
            _append_dep(task, core_business, titles)

        if _contains_any(text, ("发布", "回滚", "灰度", "变更")):
            _append_dep(task, observability, titles)

        _remove_unknown_and_self_dependencies(task, titles)
        if title and "depends_on" not in task:
            task["depends_on"] = []

    return resolved
