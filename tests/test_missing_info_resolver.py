from app.services.missing_info_resolver import build_assumption_pack


def test_build_assumption_pack_classifies_missing_info_generically():
    pack = build_assumption_pack(
        missing_info=[
            "核心身份认证方式尚未确定",
            "外部服务接口 SLA 未明确",
            "后续增强报表口径未确认",
        ],
        requirement_doc={"summary": "建设业务管理系统"},
        project_decisions={},
        human_feedback_notes=[],
    )

    assert pack["human_gate_exhausted"] is True
    assert "核心身份认证方式尚未确定" in pack["blocking"]
    assert pack["assumptions"][0]["source"] == "外部服务接口 SLA 未明确"
    assert pack["risk_controls"][0]["missing_info"] == "外部服务接口 SLA 未明确"
    assert "后续增强报表口径未确认" in pack["deferred_scope"]
    assert "后续增强报表口径未确认" not in pack["blocking"]


def test_build_assumption_pack_marks_confirmation_for_non_blocking_items():
    pack = build_assumption_pack(
        missing_info=["第三方接口文档未提供"],
        requirement_doc={},
        project_decisions={},
        human_feedback_notes=[],
    )

    assert pack["blocking"] == []
    assert pack["requires_user_confirmation"]
    assert pack["requires_user_confirmation"][0]["item"] == "第三方接口文档未提供"


def test_build_assumption_pack_does_not_defer_high_level_capability_by_wording_only():
    pack = build_assumption_pack(
        missing_info=["高级分析能力口径未确认"],
        requirement_doc={},
        project_decisions={},
        human_feedback_notes=[],
    )

    assert pack["deferred_scope"] == []
    assert pack["assumptions"][0]["source"] == "高级分析能力口径未确认"
