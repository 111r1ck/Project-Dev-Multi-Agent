from app.services.constraint_classifier import classify_constraints


def test_classify_constraints_extracts_generic_nfr_categories():
    signals = classify_constraints(
        requirement_doc={
            "summary": "建设管理系统",
            "constraints": [
                "关键链路需要明确服务等级与故障恢复目标",
                "峰值负载需要容量评估，关键操作必须具备幂等和审计",
                "上线需支持灰度和快速回滚",
            ],
        },
        architecture_plan={},
        project_decisions={
            "confirmed_constraints": [
                {
                    "category": "observability",
                    "key": "monitoring_plan",
                    "value": {"metrics": ["latency", "error_rate"]},
                }
            ]
        },
        review_report={},
    )

    categories = {signal.category for signal in signals}

    assert "availability" in categories
    assert "capacity" in categories
    assert "consistency" in categories
    assert "security_compliance" in categories
    assert "release_safety" in categories
    assert "observability" in categories


def test_classify_constraints_deduplicates_categories_but_preserves_evidence():
    signals = classify_constraints(
        requirement_doc={"constraints": ["需要监控告警", "需要链路追踪"]},
        architecture_plan={"modules": [{"name": "监控模块"}]},
        project_decisions={},
        review_report={"issues": ["缺少日志聚合能力"]},
    )

    observability = [signal for signal in signals if signal.category == "observability"]

    assert len(observability) == 1
    assert len(observability[0].evidence) >= 3
