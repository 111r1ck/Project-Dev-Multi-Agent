from app.services.missing_info_resolver import (
    build_assumption_pack,
    classify_missing_info_levels,
)


def test_build_assumption_pack_classifies_missing_info_generically():
    pack = build_assumption_pack(
        missing_info=[
            "核心身份认证方式尚未确定",
            "外部服务接口服务等级未明确",
            "后续增强报表口径未确认",
        ],
        requirement_doc={"summary": "建设业务管理系统"},
        project_decisions={},
        human_feedback_notes=[],
    )

    assert pack["human_gate_exhausted"] is True
    assert "核心身份认证方式尚未确定" in pack["blocking"]
    assert pack["assumptions"][0]["source"] == "外部服务接口服务等级未明确"
    assert any(
        item["missing_info"] == "外部服务接口服务等级未明确"
        for item in pack["risk_controls"]
    )
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
    assert pack["conditional_pass_ready"] is True
    assert pack["coverage_map"][0]["missing_info"] == "第三方接口文档未提供"
    assert pack["prelaunch_checklist"][0]["status"] == "pending"


def test_build_assumption_pack_does_not_defer_high_level_capability_by_wording_only():
    pack = build_assumption_pack(
        missing_info=["高级分析能力口径未确认"],
        requirement_doc={},
        project_decisions={},
        human_feedback_notes=[],
    )

    assert pack["deferred_scope"] == []
    assert pack["assumptions"][0]["source"] == "高级分析能力口径未确认"


def test_build_assumption_pack_converts_blocking_info_to_scope_reduction():
    pack = build_assumption_pack(
        missing_info=[
            "核心外部依赖协议未明确",
            "强合规审批规则未确认",
        ],
        requirement_doc={"summary": "建设业务系统"},
        project_decisions={},
        human_feedback_notes=[],
    )

    assert "核心外部依赖协议未明确" in pack["blocking"]
    assert "强合规审批规则未确认" in pack["blocking"]
    assert pack["scope_reductions"]
    assert pack["scope_reductions"][0]["missing_info"] == "核心外部依赖协议未明确"
    assert "替代方案" in pack["scope_reductions"][0]["action"]
    assert pack["requires_user_confirmation"][0]["phase"] == "架构评审前确认"
    assert pack["conditional_pass_ready"] is False


def test_classify_missing_info_levels():
    levels = classify_missing_info_levels(
        [
            "核心身份认证方式尚未确定",
            "外部服务接口服务等级未明确",
            "后续增强报表口径未确认",
        ]
    )

    assert levels["must_confirm"] == ["核心身份认证方式尚未确定"]
    assert levels["assumable"] == ["外部服务接口服务等级未明确"]
    assert levels["deferred"] == ["后续增强报表口径未确认"]
