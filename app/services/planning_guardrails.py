from __future__ import annotations

from app.services.constraint_classifier import ConstraintSignal


_GUARDRAIL_TASKS: dict[str, dict] = {
    "availability": {
        "title": "设计可用性目标分解与故障恢复方案",
        "description": "将服务等级目标拆解为健康检查、故障检测、恢复流程、备份恢复和演练验收，确保可用性约束可执行、可验证。",
        "priority": "P0",
        "owner_role": "架构师",
    },
    "capacity": {
        "title": "建立容量模型与负载基准测试",
        "description": "基于已确认的规模、吞吐或峰值负载约束，建立容量模型、测试数据、压测脚本、资源基线和回归阈值。",
        "priority": "P0",
        "owner_role": "测试工程师",
    },
    "latency": {
        "title": "建立关键路径延迟基准与性能回归检测",
        "description": "识别关键路径并定义响应时间、分位延迟、超时和退化阈值，纳入自动化性能回归检测。",
        "priority": "P0",
        "owner_role": "测试工程师",
    },
    "resilience": {
        "title": "实现限流降级、重试补偿与故障演练方案",
        "description": "为关键路径设计限流、降级、熔断、重试、补偿和故障演练机制，明确触发条件、上限和人工介入边界。",
        "priority": "P0",
        "owner_role": "后端开发工程师",
    },
    "scalability": {
        "title": "设计扩展策略与资源弹性预案",
        "description": "定义水平扩展、资源弹性、分片或多实例策略，明确扩展触发条件、容量水位和回退方案。",
        "priority": "P1",
        "owner_role": "架构师",
    },
    "consistency": {
        "title": "设计幂等、状态机、补偿与一致性校验机制",
        "description": "梳理关键写操作和异步流程，定义幂等键、状态流转、补偿动作、重试边界和一致性校验任务。",
        "priority": "P0",
        "owner_role": "后端开发工程师",
    },
    "security_compliance": {
        "title": "完善权限隔离、审计与合规控制",
        "description": "定义访问控制、数据隔离、审计字段、敏感操作留痕和合规验证要求，防止越权和不可追踪操作。",
        "priority": "P0",
        "owner_role": "安全工程师",
    },
    "observability": {
        "title": "建立指标采集、告警与日志追踪体系",
        "description": "定义业务与技术指标、告警规则、日志聚合、链路追踪和看板验收，支撑运行态问题定位。",
        "priority": "P0",
        "owner_role": "运维工程师",
    },
    "release_safety": {
        "title": "制定灰度发布、回滚与变更验证机制",
        "description": "设计发布批次、流量切换、健康检查、自动/手动回滚和变更后验证流程，降低上线风险。",
        "priority": "P1",
        "owner_role": "DevOps工程师",
    },
    "data_governance": {
        "title": "设计核心数据模型与持久化方案",
        "description": "定义核心业务实体、关系、持久化结构、导入导出或迁移边界，并明确备份、恢复、归档和数据保留策略。",
        "priority": "P1",
        "owner_role": "数据工程师",
    },
}


def _task_text(task: dict) -> str:
    return f"{task.get('title', '')} {task.get('description', '')}"


def _combined_task_text(tasks: list[dict]) -> str:
    return " ".join(_task_text(task) for task in tasks)


def _already_covered(tasks: list[dict], title: str) -> bool:
    return any(title == str(task.get("title", "")).strip() for task in tasks)


def _priority_rank(priority: str) -> int:
    normalized = str(priority or "").strip().upper()
    mapping = {
        "最高": 0,
        "高": 0,
        "P0": 0,
        "中": 1,
        "P1": 1,
        "低": 2,
        "P2": 2,
        "P3": 3,
    }
    return mapping.get(normalized, 1)


def _priority_label(rank: int) -> str:
    return {0: "P0", 1: "P1", 2: "P2", 3: "P3"}.get(rank, "P1")


def ensure_guardrail_tasks(
    tasks: list[dict],
    signals: list[ConstraintSignal],
) -> list[dict]:
    normalized = list(tasks)
    categories = {signal.category for signal in signals}
    for category in categories:
        template = _GUARDRAIL_TASKS.get(category)
        if not template or _already_covered(normalized, template["title"]):
            continue
        normalized.append({**template, "depends_on": []})
    return normalized


def ensure_architecture_module_tasks(
    tasks: list[dict],
    architecture_plan: dict,
) -> list[dict]:
    normalized = list(tasks)
    task_text = _combined_task_text(normalized)
    for module in (architecture_plan or {}).get("modules", []) or []:
        if not isinstance(module, dict):
            continue
        name = str(module.get("name", "")).strip()
        if not name or name in task_text:
            continue
        responsibilities = module.get("responsibilities", []) or module.get("tasks", []) or []
        if isinstance(responsibilities, str):
            responsibilities = [responsibilities]
        responsibility_text = "；".join(str(item).strip() for item in responsibilities[:3] if str(item).strip())
        description = f"基于架构模块补齐：实现{name}的核心能力、接口、异常处理与验收测试。"
        if responsibility_text:
            description += f" 模块职责：{responsibility_text}。"
        normalized.append(
            {
                "title": f"实现{name}核心功能",
                "description": description,
                "priority": "P1",
                "depends_on": ["设计核心数据模型与持久化方案"]
                if _already_covered(normalized, "设计核心数据模型与持久化方案")
                else [],
                "owner_role": "后端开发工程师",
            }
        )
        task_text += f" {name} {description}"
    return normalized


def align_dependency_priorities(tasks: list[dict]) -> list[dict]:
    normalized = [dict(task) for task in tasks]
    by_title = {
        str(task.get("title", "")).strip(): task for task in normalized if task.get("title")
    }
    changed = True
    while changed:
        changed = False
        for task in normalized:
            task_rank = _priority_rank(str(task.get("priority", "")))
            for dep_title in task.get("depends_on", []) or []:
                dep = by_title.get(str(dep_title).strip())
                if not dep:
                    continue
                dep_rank = _priority_rank(str(dep.get("priority", "")))
                if dep_rank > task_rank:
                    dep["priority"] = _priority_label(task_rank)
                    changed = True
    return normalized


def apply_assumption_pack_tasks(
    tasks: list[dict],
    assumption_pack: dict,
) -> list[dict]:
    normalized = list(tasks)
    if not assumption_pack or not assumption_pack.get("human_gate_exhausted"):
        return normalized

    deferred = [str(item) for item in (assumption_pack.get("deferred_scope", []) or [])]
    if deferred:
        filtered: list[dict] = []
        for task in normalized:
            text = f"{task.get('title', '')} {task.get('description', '')}"
            if any(item and item in text for item in deferred):
                continue
            filtered.append(task)
        normalized = filtered

    if assumption_pack.get("assumptions"):
        if not _already_covered(normalized, "验证关键假设与替代方案"):
            normalized.append(
                {
                    "title": "验证关键假设与替代方案",
                    "description": "针对人工补充上限后采用的保守假设，验证替代实现、mock方案、降级路径和验收边界。",
                    "priority": "P0",
                    "depends_on": [],
                    "owner_role": "架构师",
                }
            )

    if assumption_pack.get("scope_reductions"):
        if not _already_covered(normalized, "确认范围收缩与替代方案边界"):
            normalized.append(
                {
                    "title": "确认范围收缩与替代方案边界",
                    "description": "针对人工补充上限后的阻塞信息，明确MVP范围收缩、替代实现、mock验证、人工兜底和范围恢复条件。",
                    "priority": "P0",
                    "depends_on": [],
                    "owner_role": "产品经理",
                }
            )

    if assumption_pack.get("risk_controls"):
        if not _already_covered(normalized, "落实受控假设的风险控制措施"):
            normalized.append(
                {
                    "title": "落实受控假设的风险控制措施",
                    "description": "为受控假设补齐超时重试、降级、人工兜底、观测指标和异常处置边界。",
                    "priority": "P0",
                    "depends_on": ["验证关键假设与替代方案"]
                    if _already_covered(normalized, "验证关键假设与替代方案")
                    else [],
                    "owner_role": "后端开发工程师",
                }
            )

    if assumption_pack.get("requires_user_confirmation"):
        if not _already_covered(normalized, "上线前确认清单与决策复核"):
            normalized.append(
                {
                    "title": "上线前确认清单与决策复核",
                    "description": "汇总上线前必须确认的假设、外部依赖、后置范围和人工决策，形成可签核清单。",
                    "priority": "P0",
                    "depends_on": [],
                    "owner_role": "产品经理",
                }
            )

    return normalized
