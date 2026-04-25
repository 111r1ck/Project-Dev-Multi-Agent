from app.services.decision_parser import merge_project_decisions


def test_merge_project_decisions_keeps_latest_same_category_decision():
    current = {
        "confirmed_constraints": [
            {
                "category": "capacity",
                "key": "throughput_target",
                "value": {"total": 1000},
                "source_round": 1,
            }
        ],
        "superseded_decisions": [],
    }
    feedback = {
        "吞吐目标": {
            "总峰值": 2000,
            "接口构成": [{"name": "query", "qps": 1200}],
        }
    }

    merged = merge_project_decisions(current, feedback, source_round=2)

    active = merged["confirmed_constraints"]
    assert len(active) == 1
    assert active[0]["category"] == "capacity"
    assert active[0]["key"] == "throughput_target"
    assert active[0]["value"]["总峰值"] == 2000
    assert active[0]["source_round"] == 2
    assert merged["superseded_decisions"][0]["value"] == {"total": 1000}


def test_merge_project_decisions_classifies_multiple_generic_decisions():
    feedback = {
        "数据隔离策略": {"结论": "按租户逻辑隔离，保留迁移接口"},
        "发布计划": {"灰度": "先小流量验证，再全量发布"},
        "异常修复规则": {"重试": "失败后退避重试，超过上限转人工"},
    }

    merged = merge_project_decisions({}, feedback, source_round=1)
    categories = {item["category"] for item in merged["confirmed_constraints"]}

    assert {"security_compliance", "release_safety", "resilience"} <= categories
