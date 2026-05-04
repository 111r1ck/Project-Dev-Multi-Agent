from __future__ import annotations

from typing import Any


def _norm(text: str) -> str:
    return str(text or "").strip().lower()


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    t = _norm(text)
    return any(_norm(m) in t for m in markers)


def _task_text(task: dict[str, Any]) -> str:
    return f"{task.get('title', '')} {task.get('description', '')}"


def _is_architecture_conflict_issue(issue_text: str) -> bool:
    markers = (
        "架构冲突",
        "architecture conflict",
        "architecture mismatch",
        "state machine",
        "状态机",
        "幂等",
        "idempotency",
        "idempotent",
        "异步",
        "event-driven",
        "asynchronous",
        "sync",
        "synchronous",
        "mismatch",
    )
    return _contains_any(issue_text, markers)


def _is_singleton_style(architecture_style: str) -> bool:
    markers = ("模块化单体", "单体", "modular monolith", "monolith")
    return _contains_any(architecture_style, markers)


def _has_microservice_hard_signals(tasks: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    hard_markers = (
        "独立部署",
        "服务注册",
        "服务发现",
        "跨服务调用",
        "网关路由拆分",
        "service registry",
        "service discovery",
        "cross-service",
        "microservice",
        "independent deployment",
        "api gateway split",
    )
    evidence: list[str] = []
    for task in tasks or []:
        text = _task_text(task)
        for marker in hard_markers:
            if _contains_any(text, (marker,)):
                evidence.append(marker)
                break
    return bool(evidence), sorted(list(dict.fromkeys(evidence)))


def _has_backend_depends_on_frontend_scaffold(tasks: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    by_title = {
        str(item.get("title", "")).strip(): item
        for item in (tasks or [])
        if str(item.get("title", "")).strip()
    }
    backend_markers = ("后端", "backend", "engine", "service", "api", "流程")
    frontend_scaffold_markers = (
        "前端框架",
        "前端脚手架",
        "路由配置",
        "frontend scaffold",
        "frontend framework",
        "routing",
        "router",
        "web scaffold",
    )
    evidence: list[str] = []
    for task in tasks or []:
        task_text = _task_text(task)
        if not _contains_any(task_text, backend_markers):
            continue
        for dep in (task.get("depends_on", []) or []):
            dep_task = by_title.get(str(dep).strip())
            if not dep_task:
                continue
            if _contains_any(_task_text(dep_task), frontend_scaffold_markers):
                evidence.append(f"{task.get('title', '')}->{dep_task.get('title', '')}")
    return bool(evidence), evidence[:5]


def _is_build_or_design_task(task: dict[str, Any]) -> bool:
    return _contains_any(
        _task_text(task),
        (
            "设计",
            "开发",
            "实现",
            "建模",
            "schema",
            "api",
            "模块",
            "design",
            "develop",
            "implementation",
            "implement",
            "build",
            "module",
        ),
    )


def _is_finalization_task(task: dict[str, Any]) -> bool:
    return _contains_any(
        _task_text(task),
        (
            "生产环境部署",
            "部署上线",
            "上线发布",
            "灰度发布",
            "全量切流",
            "切流",
            "上线检查清单",
            "验收签字",
            "uat验收",
            "生产切换",
            "变更窗口",
            "交接",
            "复盘",
            "go-live",
            "release",
            "rollout",
            "cutover",
            "sign-off",
            "uat",
            "change window",
            "production deployment",
            "production rollout",
        ),
    )


def _has_build_depends_on_finalization(tasks: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    by_title = {
        str(item.get("title", "")).strip(): item
        for item in (tasks or [])
        if str(item.get("title", "")).strip()
    }
    evidence: list[str] = []
    for task in tasks or []:
        if not _is_build_or_design_task(task):
            continue
        title = str(task.get("title", "")).strip()
        for dep in (task.get("depends_on", []) or []):
            dep_task = by_title.get(str(dep).strip())
            if dep_task and _is_finalization_task(dep_task):
                evidence.append(f"{title}->{dep_task.get('title', '')}")
    return bool(evidence), evidence[:6]


def _has_reasonable_deployment_order(tasks: list[dict[str, Any]]) -> bool:
    # Heuristic: if finalization tasks depend on build/design tasks, order is likely reasonable.
    by_title = {
        str(item.get("title", "")).strip(): item
        for item in (tasks or [])
        if str(item.get("title", "")).strip()
    }
    for task in tasks or []:
        if not _is_finalization_task(task):
            continue
        for dep in (task.get("depends_on", []) or []):
            dep_task = by_title.get(str(dep).strip())
            if dep_task and _is_build_or_design_task(dep_task):
                return True
    return False


def _requires_state_model_controls(
    issue_text: str, architecture_plan: dict[str, Any] | None, tasks: list[dict[str, Any]]
) -> bool:
    corpus = " ".join(
        [
            str(issue_text or ""),
            str((architecture_plan or {}).get("architecture_style", "") or ""),
            " ".join(str(x) for x in ((architecture_plan or {}).get("backend", []) or [])),
            " ".join(_task_text(item) for item in (tasks or [])),
        ]
    )
    markers = (
        "状态机",
        "幂等",
        "事务一致性",
        "补偿",
        "状态流转",
        "并发冲突",
        "state machine",
        "idempotent",
        "transaction consistency",
        "compensation",
        "state transition",
        "concurrency conflict",
    )
    return _contains_any(corpus, markers)


def _has_state_model_implementation(tasks: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    markers = (
        "状态机",
        "状态流转",
        "幂等",
        "事务",
        "补偿",
        "重试",
        "锁",
        "版本号",
        "乐观锁",
        "悲观锁",
        "state machine",
        "state transition",
        "idempotent",
        "transaction",
        "compensation",
        "retry",
        "lock",
        "optimistic lock",
        "pessimistic lock",
    )
    evidence: list[str] = []
    negation_markers = (
        "不加锁",
        "无锁",
        "不使用事务",
        "无事务",
        "without lock",
        "no lock",
        "without transaction",
        "no transaction",
    )
    for task in tasks or []:
        text = _task_text(task)
        lowered = _norm(text)
        if any(_norm(item) in lowered for item in negation_markers):
            # Explicitly stated no-lock/no-transaction signals should not be treated
            # as state-model implementation evidence.
            continue
        if _contains_any(text, markers):
            evidence.append(str(task.get("title", "")).strip() or text[:60])
    return bool(evidence), evidence[:6]


def _has_direct_mutation_only_signals(tasks: list[dict[str, Any]]) -> bool:
    # Strong sync/update-only signals without state-model protections
    markers = (
        "直接更新",
        "同步写入",
        "串行更新",
        "无锁",
        "直接覆盖",
        "direct update",
        "sync write",
        "overwrite",
        "without lock",
    )
    return any(_contains_any(_task_text(task), markers) for task in (tasks or []))


def _requires_data_boundary_controls(
    issue_text: str, architecture_plan: dict[str, Any] | None, tasks: list[dict[str, Any]]
) -> bool:
    corpus = " ".join(
        [
            str(issue_text or ""),
            str((architecture_plan or {}).get("architecture_style", "") or ""),
            " ".join(str(x) for x in ((architecture_plan or {}).get("backend", []) or [])),
            " ".join(str(x) for x in ((architecture_plan or {}).get("frontend", []) or [])),
            " ".join(_task_text(item) for item in (tasks or [])),
        ]
    )
    markers = (
        "多租户",
        "多法人",
        "组织隔离",
        "数据隔离",
        "数据主权",
        "合规隔离",
        "租户隔离",
        "tenant",
        "multi-tenant",
        "data boundary",
        "data sovereignty",
        "org isolation",
        "compliance isolation",
    )
    return _contains_any(corpus, markers)


def _has_data_boundary_implementation(tasks: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    impl_markers = (
        "租户隔离",
        "多租户",
        "多法人",
        "组织隔离",
        "行级权限",
        "数据权限",
        "分区策略",
        "脱敏",
        "加密",
        "审计",
        "tenant isolation",
        "tenant context",
        "row-level security",
        "data masking",
        "encryption",
        "audit",
        "data retention",
    )
    evidence: list[str] = []
    for task in tasks or []:
        text = _task_text(task)
        if _contains_any(text, impl_markers):
            evidence.append(str(task.get("title", "")).strip() or text[:60])
    return bool(evidence), evidence[:6]


def _requires_async_model(
    issue_text: str, architecture_plan: dict[str, Any] | None, tasks: list[dict[str, Any]]
) -> bool:
    corpus = " ".join(
        [
            str(issue_text or ""),
            str((architecture_plan or {}).get("architecture_style", "") or ""),
            " ".join(str(x) for x in ((architecture_plan or {}).get("backend", []) or [])),
            " ".join(_task_text(item) for item in (tasks or [])),
        ]
    )
    markers = (
        "异步",
        "事件驱动",
        "消息总线",
        "最终一致性",
        "async",
        "asynchronous",
        "event-driven",
        "event bus",
        "eventual consistency",
        "message queue",
    )
    return _contains_any(corpus, markers)


def _issue_prefers_async(issue_text: str) -> bool:
    markers = (
        "异步",
        "event-driven",
        "asynchronous",
        "async",
        "消息",
        "queue",
        "event",
    )
    return _contains_any(issue_text, markers)


def _issue_prefers_state_model(issue_text: str) -> bool:
    markers = (
        "状态机",
        "幂等",
        "state machine",
        "idempotency",
        "idempotent",
        "state transition",
    )
    return _contains_any(issue_text, markers)


def _has_async_implementation(tasks: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    markers = (
        "异步",
        "消息队列",
        "事件发布",
        "事件消费",
        "补偿",
        "重试",
        "outbox",
        "async",
        "queue",
        "event",
        "consumer",
        "producer",
        "retry",
        "compensation",
    )
    evidence: list[str] = []
    for task in tasks or []:
        text = _task_text(task)
        if _contains_any(text, markers):
            evidence.append(str(task.get("title", "")).strip() or text[:60])
    return bool(evidence), evidence[:6]


def _has_sync_only_signals(tasks: list[dict[str, Any]]) -> bool:
    sync_markers = (
        "同步",
        "实时接口",
        "串行",
        "直连",
        "sync",
        "synchronous",
        "direct call",
        "request-response",
    )
    return any(_contains_any(_task_text(task), sync_markers) for task in (tasks or []))


def check_architecture_conflict(
    *,
    issue_text: str,
    architecture_plan: dict[str, Any] | None,
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Reusable architecture conflict checker.
    Phase-1 rule:
    - singleton_vs_microservice can block only with hard microservice signals.
    """
    issue = str(issue_text or "")
    if not _is_architecture_conflict_issue(issue):
        return {
            "is_architecture_conflict_issue": False,
            "conflict_type": "none",
            "has_hard_evidence": False,
            "evidence_list": [],
            "severity": "none",
            "decision": "not_applicable",
        }

    has_reverse_finalization_dep, reverse_finalization_evidence = _has_build_depends_on_finalization(tasks)
    if has_reverse_finalization_dep:
        return {
            "is_architecture_conflict_issue": True,
            "conflict_type": "deployment_model_conflict",
            "has_hard_evidence": True,
            "evidence_list": reverse_finalization_evidence,
            "severity": "blocking",
            "decision": "blocking_deployment_reverse_dependency_confirmed",
        }

    has_reverse_dep, reverse_dep_evidence = _has_backend_depends_on_frontend_scaffold(tasks)
    if has_reverse_dep:
        return {
            "is_architecture_conflict_issue": True,
            "conflict_type": "deployment_model_conflict",
            "has_hard_evidence": True,
            "evidence_list": reverse_dep_evidence,
            "severity": "blocking",
            "decision": "blocking_reverse_dependency_confirmed",
        }

    if _has_reasonable_deployment_order(tasks):
        return {
            "is_architecture_conflict_issue": True,
            "conflict_type": "deployment_model_conflict",
            "has_hard_evidence": False,
            "evidence_list": ["deployment_depends_on_build_or_design"],
            "severity": "suggestion",
            "decision": "downgraded_deployment_order_reasonable",
        }

    if _requires_data_boundary_controls(issue, architecture_plan, tasks):
        has_impl, impl_evidence = _has_data_boundary_implementation(tasks)
        if not has_impl:
            return {
                "is_architecture_conflict_issue": True,
                "conflict_type": "data_boundary_conflict",
                "has_hard_evidence": True,
                "evidence_list": ["missing_data_boundary_implementation"],
                "severity": "blocking",
                "decision": "blocking_data_boundary_missing_implementation",
            }
        return {
            "is_architecture_conflict_issue": True,
            "conflict_type": "data_boundary_conflict",
            "has_hard_evidence": False,
            "evidence_list": impl_evidence,
            "severity": "suggestion",
            "decision": "downgraded_data_boundary_covered",
        }

    requires_async = _requires_async_model(issue, architecture_plan, tasks)
    requires_state_model = _requires_state_model_controls(issue, architecture_plan, tasks)

    if _issue_prefers_async(issue) and requires_async:
        has_async_impl, async_evidence = _has_async_implementation(tasks)
        if not has_async_impl and _has_sync_only_signals(tasks):
            return {
                "is_architecture_conflict_issue": True,
                "conflict_type": "sync_vs_async_mismatch",
                "has_hard_evidence": True,
                "evidence_list": ["requires_async_but_only_sync_signals"],
                "severity": "blocking",
                "decision": "blocking_sync_async_mismatch",
            }
        return {
            "is_architecture_conflict_issue": True,
            "conflict_type": "sync_vs_async_mismatch",
            "has_hard_evidence": False,
            "evidence_list": async_evidence,
            "severity": "suggestion",
            "decision": "downgraded_sync_async_covered",
        }

    if _issue_prefers_state_model(issue) and requires_state_model:
        has_impl, impl_evidence = _has_state_model_implementation(tasks)
        if not has_impl and _has_direct_mutation_only_signals(tasks):
            return {
                "is_architecture_conflict_issue": True,
                "conflict_type": "state_model_conflict",
                "has_hard_evidence": True,
                "evidence_list": ["requires_state_model_but_only_direct_mutation_signals"],
                "severity": "blocking",
                "decision": "blocking_state_model_missing_implementation",
            }
        return {
            "is_architecture_conflict_issue": True,
            "conflict_type": "state_model_conflict",
            "has_hard_evidence": False,
            "evidence_list": impl_evidence,
            "severity": "suggestion",
            "decision": "downgraded_state_model_covered",
        }

    if requires_async:
        has_async_impl, async_evidence = _has_async_implementation(tasks)
        if not has_async_impl and _has_sync_only_signals(tasks):
            return {
                "is_architecture_conflict_issue": True,
                "conflict_type": "sync_vs_async_mismatch",
                "has_hard_evidence": True,
                "evidence_list": ["requires_async_but_only_sync_signals"],
                "severity": "blocking",
                "decision": "blocking_sync_async_mismatch",
            }
        return {
            "is_architecture_conflict_issue": True,
            "conflict_type": "sync_vs_async_mismatch",
            "has_hard_evidence": False,
            "evidence_list": async_evidence,
            "severity": "suggestion",
            "decision": "downgraded_sync_async_covered",
        }

    if requires_state_model:
        has_impl, impl_evidence = _has_state_model_implementation(tasks)
        if not has_impl and _has_direct_mutation_only_signals(tasks):
            return {
                "is_architecture_conflict_issue": True,
                "conflict_type": "state_model_conflict",
                "has_hard_evidence": True,
                "evidence_list": ["requires_state_model_but_only_direct_mutation_signals"],
                "severity": "blocking",
                "decision": "blocking_state_model_missing_implementation",
            }
        return {
            "is_architecture_conflict_issue": True,
            "conflict_type": "state_model_conflict",
            "has_hard_evidence": False,
            "evidence_list": impl_evidence,
            "severity": "suggestion",
            "decision": "downgraded_state_model_covered",
        }

    style = str((architecture_plan or {}).get("architecture_style", "") or "")
    if _is_singleton_style(style):
        has_hard, evidence = _has_microservice_hard_signals(tasks)
        return {
            "is_architecture_conflict_issue": True,
            "conflict_type": "singleton_vs_microservice",
            "has_hard_evidence": has_hard,
            "evidence_list": evidence,
            "severity": "blocking" if has_hard else "suggestion",
            "decision": (
                "blocking_conflict_confirmed"
                if has_hard
                else "downgraded_no_hard_microservice_evidence"
            ),
        }

    return {
        "is_architecture_conflict_issue": True,
        "conflict_type": "generic_architecture_conflict",
        "has_hard_evidence": False,
        "evidence_list": [],
        "severity": "suggestion",
        "decision": "downgraded_generic_architecture_conflict",
    }
