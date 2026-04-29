import re
from difflib import SequenceMatcher

from app.agents.reviewer_agent import build_reviewer_agent
from app.config import settings
from app.graph.nodes.common import (
    analyze_blocking_issue_coverage,
    detect_dependency_cycles,
    extract_blocking_issues,
    extract_structured_response,
    summarize_key_list,
    summarize_prompt_pack,
    summarize_review_feedback,
    summarize_task_breakdown,
)
from app.graph.state import ProjectState
from app.services.reviewer_cache import load_cached_review, save_cached_review


def _is_prompt_quality_only_review(review_report: dict) -> bool:
    if not isinstance(review_report, dict):
        return False
    issues = [str(item) for item in (review_report.get("issues", []) or [])]
    if not issues:
        return False
    prompt_markers = (
        "提示词",
        "prompt",
        "编码提示",
        "测试提示",
        "兜底提示",
    )
    blocking_markers = (
        "阻塞",
        "关键功能缺失",
        "架构冲突",
        "数据丢失",
        "合规",
        "性能验证",
    )
    has_prompt_issue = any(
        any(marker.lower() in issue.lower() for marker in prompt_markers)
        for issue in issues
    )
    has_non_prompt_blocking = any(
        any(marker.lower() in issue.lower() for marker in blocking_markers)
        for issue in issues
    )
    return has_prompt_issue and not has_non_prompt_blocking


def _is_coverage_only_issue(issue: str) -> bool:
    text = str(issue or "")
    markers = (
        "回流覆盖检查未通过",
        "尚未被任务清单命中",
        "显式包含阻塞项关键词",
        "补充依赖关系与验收标准",
    )
    return any(marker in text for marker in markers)


def _build_conditional_pass_if_possible(
    state: ProjectState,
    review_report: dict,
) -> dict | None:
    assumption_pack = state.get("assumption_pack", {}) or {}
    if not assumption_pack.get("human_gate_exhausted"):
        return None
    if assumption_pack.get("blocking"):
        return None

    issues = [str(item) for item in (review_report.get("issues", []) or [])]
    if not issues or not all(_is_coverage_only_issue(issue) for issue in issues):
        return None

    tasks = state.get("task_breakdown", []) or []
    task_text = " ".join(f"{t.get('title', '')} {t.get('description', '')}" for t in tasks)
    anchors = (
        "验证关键假设与替代方案",
        "落实受控假设的风险控制措施",
        "上线前确认清单与决策复核",
    )
    covered_anchors = [anchor for anchor in anchors if anchor in task_text]
    checklist = assumption_pack.get("prelaunch_checklist", []) or []
    if len(covered_anchors) < 2 and not checklist:
        return None

    conditions = checklist or [
        {"item": item.get("item", ""), "phase": item.get("phase", "上线前确认"), "status": "pending"}
        for item in (assumption_pack.get("requires_user_confirmation", []) or [])
    ]
    return {
        "passed": True,
        "passed_with_conditions": True,
        "conditions": conditions,
        "issues": issues,
        "suggestions": [
            "已转为条件通过：请在上线前完成条件清单签核，并将未确认项保持在范围外。"
        ],
    }


def _apply_review_outcome(
    state: ProjectState,
    review_report: dict,
    passed: bool,
) -> ProjectState:
    review_rounds = int(state.get("review_rounds", 0))
    max_review_rounds = int(state.get("max_review_rounds", settings.review_max_rounds))

    if passed:
        return {
            **state,
            "review_report": review_report,
            "next_step": "finish",
        }

    next_review_rounds = review_rounds + 1
    if next_review_rounds >= max_review_rounds:
        conditional_pass = _build_conditional_pass_if_possible(state, review_report)
        if conditional_pass is not None:
            return {
                **state,
                "review_report": conditional_pass,
                "review_rounds": next_review_rounds,
                "next_step": "finish",
            }
        errors = list(state.get("errors", []))
        errors.append(
            f"评审未通过，已达到最大复审轮次({max_review_rounds})，请根据review_report人工修正后再运行。"
        )
        return {
            **state,
            "review_report": review_report,
            "review_rounds": next_review_rounds,
            "errors": errors,
            "next_step": "finish",
        }

    return {
        **state,
        "review_report": review_report,
        "review_rounds": next_review_rounds,
        "next_step": "prompt_builder"
        if _is_prompt_quality_only_review(review_report)
        else "planner",
    }


def _has_blocking_issue(review_report: dict) -> bool:
    if not isinstance(review_report, dict):
        return False
    issues = [str(item) for item in (review_report.get("issues", []) or [])]
    if not issues:
        return False
    blocking_markers = [
        "阻塞",
        "关键",
        "缺失",
        "无法",
        "不能",
        "风险",
        "合规",
        "审计",
        "日志持久化",
        "性能验证",
        "性能测试",
        "无法验证",
        "数据丢失",
        "依赖关系",
        "冲突",
        "must",
        "blocker",
        "critical",
    ]
    normalized_issues = [issue.lower() for issue in issues]
    return any(
        marker.lower() in issue
        for issue in normalized_issues
        for marker in blocking_markers
    )


def _normalize_review_passed(review_report: dict) -> tuple[dict, bool]:
    normalized = dict(review_report)
    passed = bool(normalized.get("passed"))
    if passed and _has_blocking_issue(normalized):
        normalized["passed"] = False
        passed = False
    return normalized, passed


def _is_hard_blocking_issue_text(issue: str) -> bool:
    text = str(issue or "").lower()
    markers = (
        "关键",
        "缺失",
        "阻塞",
        "无法",
        "不能",
        "风险",
        "合规",
        "审计",
        "日志持久化",
        "性能验证",
        "性能测试",
        "数据丢失",
        "架构冲突",
        "blocker",
        "critical",
        "must",
    )
    return any(marker in text for marker in markers)


def _is_dependency_cycle_issue_text(issue: str) -> bool:
    text = str(issue or "").lower()
    markers = ("循环依赖", "依赖环", "环形依赖", "互相依赖", "circular dependency")
    return any(marker in text for marker in markers)


def _is_dependency_timing_issue_text(issue: str) -> bool:
    text = str(issue or "").lower()
    markers = (
        "时机错误",
        "依赖项错误",
        "依赖关系",
        "依赖链",
        "阻塞核心开发",
        "被阻塞",
        "导致延迟",
        "延后",
        "应依赖",
        "应该依赖",
        "需依赖",
        "需要依赖",
        "deps=0",
        "前置",
        "后置",
    )
    return any(marker in text for marker in markers)


def _render_cycle_issue(cycle: list[str]) -> str:
    cleaned = [str(node).strip() for node in (cycle or []) if str(node).strip()]
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1]:
        chain = cleaned
    else:
        chain = cleaned + ([cleaned[0]] if cleaned else [])
    if not chain:
        return "【循环依赖-阻塞】检测到任务依赖环，请解除至少一条依赖边。"
    return (
        "【循环依赖-阻塞】检测到循环依赖链："
        + " → ".join(chain)
        + "。请解除至少一条依赖边。"
    )


def _cycle_claim_alignment(issue: str, cycles: list[list[str]]) -> dict:
    claim_nodes = [item for item in _extract_quoted_phrases(issue) if item]
    if not claim_nodes:
        return {
            "claim_nodes": [],
            "aligned": False,
            "best_overlap": 0,
            "best_cycle": [],
        }
    claim_set = set(claim_nodes)
    best_overlap = 0
    best_cycle: list[str] = []
    for cycle in cycles or []:
        cycle_nodes = [str(node).strip() for node in (cycle or []) if str(node).strip()]
        cycle_set = set(cycle_nodes)
        overlap = len(claim_set & cycle_set)
        if overlap > best_overlap:
            best_overlap = overlap
            best_cycle = cycle_nodes
    aligned = best_overlap >= max(1, min(2, len(claim_set)))
    return {
        "claim_nodes": claim_nodes,
        "aligned": aligned,
        "best_overlap": best_overlap,
        "best_cycle": best_cycle,
    }


_POSTPROCESS_STOP_WORDS: set[str] = {
    "需求",
    "明确",
    "要求",
    "缺失",
    "功能",
    "方案",
    "实现",
    "相关",
    "任务",
    "建议",
    "采用",
    "模式",
    "MVP",
}


def _pp_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}", str(text or ""))
    return {t for t in tokens if t and t not in _POSTPROCESS_STOP_WORDS}


def _cjk_bigrams(text: str) -> set[str]:
    normalized = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", str(text or ""))
    chars = [ch for ch in normalized if "\u4e00" <= ch <= "\u9fff"]
    if len(chars) < 2:
        return set()
    return {"".join(chars[i : i + 2]) for i in range(len(chars) - 1)}


def _normalize_phrase(text: str) -> str:
    normalized = re.sub(r"^【[^】]+】", "", str(text or "")).strip()
    normalized = normalized.strip("'\"‘’“”`")
    normalized = re.sub(r"[（(].*?[)）]$", "", normalized).strip()
    normalized = re.sub(r"(相关任务|开发任务|任务|模块|功能)$", "", normalized).strip()
    return normalized


def _extract_missing_claim_phrases(issue: str) -> list[str]:
    text = str(issue or "")
    patterns = [
        r"要求['‘“\"]([^'’”\"]{2,80})['’”\"]",
        r"未发现([^，。；\n]{2,80})",
        r"未见([^，。；\n]{2,80})",
        r"缺少([^，。；\n]{2,80})",
        r"缺失([^，。；\n]{2,80})",
        r"未包含([^，。；\n]{2,80})",
    ]
    phrases: list[str] = []
    for pattern in patterns:
        for value in re.findall(pattern, text):
            phrase = _normalize_phrase(value)
            if len(phrase) < 2:
                continue
            if phrase not in phrases:
                phrases.append(phrase)
    return phrases[:6]


def _build_evidence_items(tasks: list[dict], prompts: list[dict]) -> list[str]:
    items: list[str] = []
    for task in tasks or []:
        title = str(task.get("title", "")).strip()
        description = str(task.get("description", "")).strip()
        merged = " ".join([title, description]).strip()
        if merged:
            items.append(merged)
    for prompt in prompts or []:
        merged = " ".join(
            [
                str(prompt.get("task_title", "")).strip(),
                str(prompt.get("coding_prompt", "")).strip(),
                str(prompt.get("test_prompt", "")).strip(),
            ]
        ).strip()
        if merged:
            items.append(merged)
    return items


def _phrase_supported_by_items(phrase: str, items: list[str]) -> bool:
    phrase_norm = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", _normalize_phrase(phrase))
    if len(phrase_norm) < 2:
        return False
    phrase_tokens = _pp_tokens(phrase)
    phrase_bigrams = _cjk_bigrams(phrase)

    for item in items:
        item_norm = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", str(item or ""))
        if not item_norm:
            continue
        if phrase_norm in item_norm:
            return True

        item_tokens = _pp_tokens(item)
        if phrase_tokens:
            token_hit = len(phrase_tokens & item_tokens)
            required_token_hit = min(2, len(phrase_tokens))
            if token_hit >= required_token_hit:
                return True

        item_bigrams = _cjk_bigrams(item)
        if phrase_bigrams and item_bigrams:
            overlap = len(phrase_bigrams & item_bigrams)
            if overlap >= max(2, int(len(phrase_bigrams) * 0.45)):
                return True

        if len(phrase_norm) >= 4 and SequenceMatcher(None, phrase_norm, item_norm).ratio() >= 0.62:
            return True
    return False


def _issue_claims_missing_but_present(
    issue: str,
    tasks: list[dict],
    prompts: list[dict],
    diag: dict | None = None,
) -> bool:
    missing_markers = ("未发现", "未见", "缺少", "缺失", "未包含", "未覆盖")
    issue_text = str(issue or "")
    if not any(marker in issue_text for marker in missing_markers):
        return False

    phrases = _extract_missing_claim_phrases(issue_text)
    missing_capability = str((diag or {}).get("missing_capability", "")).strip()
    if missing_capability:
        normalized_capability = _normalize_phrase(missing_capability)
        if normalized_capability and normalized_capability not in phrases:
            phrases.append(normalized_capability)
    if not phrases:
        return False

    evidence_items = _build_evidence_items(tasks, prompts)
    if not evidence_items:
        return False
    return any(_phrase_supported_by_items(phrase, evidence_items) for phrase in phrases)


def _issue_terms_supported_by_evidence(
    issue: str,
    tasks: list[dict],
    prompts: list[dict],
    diag: dict | None = None,
) -> bool:
    issue_text = str(issue or "")
    missing_markers = ("未发现", "未见", "缺少", "缺失", "未包含", "遗漏")
    if not any(marker in issue_text for marker in missing_markers):
        return False

    issue_terms = [str(item).strip() for item in ((diag or {}).get("issue_terms", []) or []) if str(item).strip()]
    if not issue_terms:
        return False

    corpus = " ".join(
        [
            " ".join(f"{str(t.get('title', ''))} {str(t.get('description', ''))}" for t in (tasks or [])),
            " ".join(
                f"{str(p.get('task_title', ''))} {str(p.get('coding_prompt', ''))} {str(p.get('test_prompt', ''))}"
                for p in (prompts or [])
            ),
        ]
    )
    corpus_tokens = _pp_tokens(corpus)
    corpus_bigrams = _cjk_bigrams(corpus)

    matched = 0
    for term in issue_terms[:8]:
        term_tokens = _pp_tokens(term)
        term_bigrams = _cjk_bigrams(term)
        token_hit = bool(term_tokens and (term_tokens & corpus_tokens))
        bigram_hit = bool(term_bigrams and len(term_bigrams & corpus_bigrams) >= max(1, int(len(term_bigrams) * 0.4)))
        if token_hit or bigram_hit:
            matched += 1

    # Require at least two term hits to avoid overly loose downgrades.
    return matched >= 2


def _extract_quoted_phrases(text: str) -> list[str]:
    raw = re.findall(r"['‘“\"]([^'’”\"]{2,120})['’”\"]", str(text or ""))
    phrases: list[str] = []
    for item in raw:
        phrase = str(item).strip()
        if phrase and phrase not in phrases:
            phrases.append(phrase)
    return phrases


def _is_research_like_task(task: dict) -> bool:
    text = " ".join(
        [
            str(task.get("title", "")).strip(),
            str(task.get("description", "")).strip(),
        ]
    )
    markers = (
        "技术预研",
        "可行性验证",
        "兼容性验证",
        "兼容性测试",
        "poc",
        "方案选型",
        "验证",
    )
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def _issue_is_research_timing_dispute(
    issue: str,
    tasks: list[dict],
) -> bool:
    if not _is_dependency_timing_issue_text(issue):
        return False
    quoted = _extract_quoted_phrases(issue)
    if not quoted:
        return False
    by_title = {
        str(task.get("title", "")).strip(): task
        for task in (tasks or [])
        if str(task.get("title", "")).strip()
    }
    for phrase in quoted:
        task = by_title.get(phrase)
        if not task:
            continue
        deps = [str(dep).strip() for dep in (task.get("depends_on", []) or []) if str(dep).strip()]
        if not deps and _is_research_like_task(task):
            return True
    return False


def _issue_suggestion_has_contradiction_evidence(
    issue: str,
    suggestions: list[str],
    tasks: list[dict],
    prompts: list[dict],
    diag: dict | None = None,
) -> bool:
    issue_tokens = _pp_tokens(issue)
    if not issue_tokens:
        return False

    corpus = " ".join(
        [
            " ".join(
                f"{str(item.get('title', ''))} {str(item.get('description', ''))}" for item in (tasks or [])
            ),
            " ".join(
                f"{str(item.get('task_title', ''))} {str(item.get('coding_prompt', ''))} {str(item.get('test_prompt', ''))}"
                for item in (prompts or [])
            ),
        ]
    )
    corpus_tokens = _pp_tokens(corpus)
    issue_corpus_token_overlap = len(issue_tokens & corpus_tokens)

    source_scores = (diag or {}).get("source_scores", {}) if isinstance(diag, dict) else {}
    max_source_score = 0.0
    if isinstance(source_scores, dict) and source_scores:
        max_source_score = max(float(v or 0.0) for v in source_scores.values())

    uncertainty_markers = ("未确定", "待确认", "未明确", "尚未确定", "不明确")
    recommendation_markers = ("建议", "方案", "采用", "可选", "推荐")
    has_uncertainty_issue = any(marker in str(issue or "") for marker in uncertainty_markers)
    issue_bigrams = _cjk_bigrams(issue)
    corpus_bigrams = _cjk_bigrams(corpus)

    for suggestion in suggestions:
        sug_tokens = _pp_tokens(suggestion)
        sug_bigrams = _cjk_bigrams(suggestion)
        if not sug_tokens:
            # keep evaluating with char-level evidence
            pass
        else:
            if len(issue_tokens & sug_tokens) < 1:
                # no token-level hit, allow char-level fallback below
                pass
            else:
                corpus_overlap = len(sug_tokens & corpus_tokens)
                if corpus_overlap >= 2 and max_source_score >= 0.45:
                    return True
                if (
                    has_uncertainty_issue
                    and (corpus_overlap >= 2 or issue_corpus_token_overlap >= 1)
                    and any(marker in suggestion for marker in recommendation_markers)
                ):
                    return True

        # Fallback for Chinese phrasing variance: use char bigram overlap.
        issue_suggestion_bigram_hit = len(issue_bigrams & sug_bigrams) >= 2
        suggestion_corpus_bigram_hit = len(sug_bigrams & corpus_bigrams) >= 3
        if issue_suggestion_bigram_hit and suggestion_corpus_bigram_hit:
            return True

    return False


def _is_performance_data_sufficiency_issue(issue: str) -> bool:
    text = str(issue or "").lower()
    perf_markers = ("性能", "压测", "基准", "p95", "p99", "qps", "延迟", "吞吐")
    data_markers = ("真实数据", "数据量", "样本", "元数据", "验证", "支撑")
    return any(m in text for m in perf_markers) and any(m in text for m in data_markers)


def _has_performance_validation_spec(tasks: list[dict], prompts: list[dict]) -> bool:
    corpus = " ".join(
        [
            " ".join(
                f"{str(item.get('title', ''))} {str(item.get('description', ''))}" for item in (tasks or [])
            ),
            " ".join(
                f"{str(item.get('task_title', ''))} {str(item.get('coding_prompt', ''))} {str(item.get('test_prompt', ''))}"
                for item in (prompts or [])
            ),
        ]
    ).lower()
    has_metric = any(marker in corpus for marker in ("p95", "p99", "qps", "延迟", "吞吐", "性能"))
    has_threshold = any(marker in corpus for marker in ("<=", "≥", ">=", "ms", "秒", "qps"))
    has_data_scale = bool(re.search(r"\d+\s*(万|千|百万|亿|条|份|gb|mb|k)", corpus))
    has_data_source = any(marker in corpus for marker in ("真实数据", "样本", "脱敏", "合成", "迁移", "元数据"))
    hits = sum([has_metric, has_threshold, has_data_scale, has_data_source])
    return has_metric and hits >= 3


def _postprocess_review_report_with_evidence(
    *,
    tasks: list[dict],
    prompts: list[dict],
    review_report: dict,
) -> tuple[dict, bool]:
    normalized = dict(review_report or {})
    issues = [str(item) for item in (normalized.get("issues", []) or [])]
    suggestions = [str(item) for item in (normalized.get("suggestions", []) or [])]
    if not issues:
        passed = bool(normalized.get("passed"))
        return normalized, passed

    coverage_analysis = analyze_blocking_issue_coverage(
        tasks,
        issues,
        prompt_pack=prompts,
        min_evidence_hits=settings.coverage_min_evidence_hits,
        min_confidence=settings.coverage_min_confidence,
        blocking_confidence=settings.coverage_blocking_confidence,
    )
    uncovered = [str(item) for item in (coverage_analysis.get("uncovered", []) or [])]
    uncovered_set = set(uncovered)
    diagnostics = coverage_analysis.get("diagnostics", []) or []
    covered_issue_set = {
        str(item.get("issue_text", "")).strip()
        for item in diagnostics
        if isinstance(item, dict) and str(item.get("decision", "")) == "covered"
    }
    dependency_check = detect_dependency_cycles(tasks)
    post_diagnostics: list[dict] = []
    diag_by_issue = {
        str(item.get("issue_text", "")): item for item in diagnostics if isinstance(item, dict)
    }

    kept_issues: list[str] = []
    downgraded_issues: list[str] = []
    explicit_downgraded: set[str] = set()
    cycle_issue_seen = False
    rendered_cycle_issues: list[str] = []

    def _append_downgrade_diag(issue_text: str, issue_type: str, decision: str, reason: str) -> None:
        post_diagnostics.append(
            {
                "issue_text": issue_text,
                "issue_type": issue_type,
                "decision": decision,
                "reason": reason,
            }
        )

    for issue in issues:
        if _issue_is_research_timing_dispute(issue, tasks):
            downgraded_issues.append(issue)
            explicit_downgraded.add(issue)
            _append_downgrade_diag(
                issue,
                "dependency_timing",
                "downgraded_research_timing_dispute",
                "research_task_can_be_preflight_with_empty_depends_on",
            )
            continue

        if _is_dependency_cycle_issue_text(issue):
            cycle_issue_seen = True
            if dependency_check.get("has_cycle"):
                cycles = dependency_check.get("cycles", []) or []
                alignment = _cycle_claim_alignment(issue, cycles)
                if not alignment.get("aligned"):
                    downgraded_issues.append(issue)
                    explicit_downgraded.add(issue)
                    _append_downgrade_diag(
                        issue,
                        "dependency_cycle",
                        "downgraded_cycle_claim_not_aligned",
                        "cycle_claim_mismatch_with_detected_cycles",
                    )
                    suggestions.append(
                        "【循环依赖说明已重写】原评审链条与结构化依赖图不一致，已按真实环路重写阻塞问题。"
                    )
                rendered_cycle_issues = [
                    _render_cycle_issue(cycle) for cycle in cycles[:3] if isinstance(cycle, list)
                ] or ["【循环依赖-阻塞】检测到任务依赖环，请解除至少一条依赖边。"]
                post_diagnostics.append(
                    {
                        "issue_text": issue,
                        "issue_type": "dependency_cycle",
                        "decision": "blocking_cycle_confirmed",
                        "has_cycle": True,
                        "cycles": cycles[:3],
                        "claim_nodes": alignment.get("claim_nodes", []),
                        "claim_aligned": alignment.get("aligned", False),
                        "best_overlap": alignment.get("best_overlap", 0),
                        "best_cycle": alignment.get("best_cycle", []),
                    }
                )
            else:
                downgraded_issues.append(issue)
                explicit_downgraded.add(issue)
                post_diagnostics.append(
                    {
                        "issue_text": issue,
                        "issue_type": "dependency_cycle",
                        "decision": "downgraded_no_cycle",
                        "reason": "no_structural_cycle_detected",
                        "has_cycle": False,
                    }
                )
            continue

        if _is_dependency_timing_issue_text(issue):
            downgraded_issues.append(issue)
            explicit_downgraded.add(issue)
            _append_downgrade_diag(
                issue,
                "dependency_timing",
                "downgraded_dependency_timing",
                "dependency_timing_dispute_should_not_block_without_structural_cycle",
            )
            continue

        if _is_performance_data_sufficiency_issue(issue) and _has_performance_validation_spec(tasks, prompts):
            downgraded_issues.append(issue)
            explicit_downgraded.add(issue)
            _append_downgrade_diag(
                issue,
                "performance_validation",
                "downgraded_perf_data_sufficient",
                "performance_spec_contains_metric_threshold_and_data_scale",
            )
            continue

        if _issue_claims_missing_but_present(
            issue,
            tasks,
            prompts,
            diag_by_issue.get(issue, {}),
        ):
            downgraded_issues.append(issue)
            explicit_downgraded.add(issue)
            _append_downgrade_diag(
                issue,
                "missing_claim",
                "downgraded_missing_claim_present",
                "missing_capability_claim_already_present_in_tasks_or_prompts",
            )
            continue

        if _issue_terms_supported_by_evidence(
            issue,
            tasks,
            prompts,
            diag_by_issue.get(issue, {}),
        ):
            downgraded_issues.append(issue)
            explicit_downgraded.add(issue)
            _append_downgrade_diag(
                issue,
                "missing_claim_terms",
                "downgraded_terms_supported",
                "issue_terms_have_multi_hit_evidence_in_tasks_or_prompts",
            )
            continue

        if issue in uncovered_set:
            if _issue_suggestion_has_contradiction_evidence(
                issue,
                suggestions,
                tasks,
                prompts,
                diag_by_issue.get(issue, {}),
            ):
                downgraded_issues.append(issue)
                explicit_downgraded.add(issue)
                _append_downgrade_diag(
                    issue,
                    "contradiction_evidence",
                    "downgraded_contradiction_evidence",
                    "suggestion_and_task_prompt_evidence_contradict_missing_claim",
                )
                continue
            kept_issues.append(issue)
            continue
        diag = diag_by_issue.get(issue, {})
        # Guardrail: hard blocking issues should not be downgraded if still uncovered.
        decision = str(diag.get("decision", ""))
        evidence_hits = int(diag.get("evidence_hits", 0) or 0)
        coverage_confidence = float(diag.get("coverage_confidence", 0.0) or 0.0)
        very_low_coverage = coverage_confidence < (settings.coverage_min_confidence * 0.55)
        source_components = diag.get("source_components", {}) if isinstance(diag, dict) else {}
        max_core_score = 0.0
        if isinstance(source_components, dict):
            for comp in source_components.values():
                if not isinstance(comp, dict):
                    continue
                core_score = (
                    0.45 * float(comp.get("keyword", 0.0) or 0.0)
                    + 0.35 * float(comp.get("semantic", 0.0) or 0.0)
                    + 0.20 * float(comp.get("structure", 0.0) or 0.0)
                )
                if core_score > max_core_score:
                    max_core_score = core_score
        weak_core_evidence = max_core_score < 0.42
        low_signal_uncovered = evidence_hits == 0 and very_low_coverage
        weak_single_source_uncovered = (
            evidence_hits <= 1
            and weak_core_evidence
            and coverage_confidence < settings.coverage_min_confidence
        )
        if (
            _is_hard_blocking_issue_text(issue)
            and not _is_dependency_timing_issue_text(issue)
            and decision == "downgraded_uncovered"
            and (low_signal_uncovered or weak_single_source_uncovered)
        ):
            kept_issues.append(issue)
        else:
            downgraded_issues.append(issue)
            _append_downgrade_diag(
                issue,
                "generic",
                "downgraded_generic",
                f"decision={decision or 'unknown'};low_signal={low_signal_uncovered};weak_single_source={weak_single_source_uncovered}",
            )

    if cycle_issue_seen and dependency_check.get("has_cycle"):
        for item in rendered_cycle_issues:
            if item and item not in kept_issues:
                kept_issues.append(item)

    downgraded_for_suggestions = [
        item for item in downgraded_issues if str(item).strip() and str(item).strip() not in covered_issue_set
    ]
    if downgraded_for_suggestions:
        suggestions.extend(
            [f"【已降级为建议（证据已覆盖或置信度不足）】{item}" for item in downgraded_for_suggestions]
        )

    # Final consistency guard:
    # Any diagnostics marked as blocking_uncovered must remain in issues unless explicitly downgraded by typed rules.
    blocking_diag_issues = {
        str(item.get("issue_text", "")).strip()
        for item in diagnostics
        if isinstance(item, dict) and str(item.get("decision", "")) == "blocking_uncovered"
    }
    for issue in blocking_diag_issues:
        if not issue or issue in explicit_downgraded:
            continue
        if issue not in kept_issues:
            kept_issues.append(issue)
        if issue in downgraded_issues:
            downgraded_issues = [item for item in downgraded_issues if item != issue]
        post_diagnostics.append(
            {
                "issue_text": issue,
                "issue_type": "consistency_guard",
                "decision": "forced_restore_blocking",
                "reason": "blocking_uncovered_must_remain_in_issues",
            }
        )

    # Safety cleanup: downgraded suggestion prefix must never appear in issues.
    cleaned_issues: list[str] = []
    for item in kept_issues:
        if item.startswith("【已降级为建议"):
            suggestions.append(item)
            continue
        cleaned_issues.append(item)
    kept_issues = cleaned_issues

    normalized["issues"] = kept_issues
    normalized["suggestions"] = suggestions
    normalized["diagnostics"] = diagnostics + post_diagnostics

    if kept_issues:
        normalized["passed"] = False
    else:
        normalized["passed"] = True
    return normalized, bool(normalized["passed"])


def _build_assumption_pack_review(assumption_pack: dict, tasks: list[dict]) -> dict | None:
    if not assumption_pack or not assumption_pack.get("human_gate_exhausted"):
        return None
    issues: list[str] = []
    suggestions: list[str] = []

    blocking = [str(item) for item in (assumption_pack.get("blocking", []) or [])]
    scope_reductions = assumption_pack.get("scope_reductions", []) or []
    has_scope_reduction = bool(scope_reductions)
    if blocking and not has_scope_reduction:
        issues.append("人工补充上限后仍存在阻塞信息，不能仅依赖受控假设继续。")
        issues.extend(blocking[:5])

    task_text = " ".join(
        f"{item.get('title', '')} {item.get('description', '')}" for item in (tasks or [])
    )
    if assumption_pack.get("assumptions") and "验证关键假设" not in task_text:
        issues.append("受控假设缺少验证任务，无法证明假设可接受。")
        suggestions.append("请补充“验证关键假设与替代方案”任务。")
    if assumption_pack.get("risk_controls") and "风险控制" not in task_text:
        issues.append("受控假设缺少风险控制落地任务。")
        suggestions.append("请补充降级、重试、人工兜底、观测指标等风险控制任务。")
    has_confirmation_task = "确认" in task_text
    has_prelaunch_checklist = bool(assumption_pack.get("prelaunch_checklist"))
    if assumption_pack.get("requires_user_confirmation") and not has_confirmation_task and not has_prelaunch_checklist:
        issues.append("上线前需确认事项未形成确认清单任务。")
        suggestions.append("请补充“上线前确认清单与决策复核”任务。")
    if blocking and has_scope_reduction and "范围收缩" not in task_text and "替代方案" not in task_text:
        issues.append("阻塞信息已转为范围收缩，但缺少范围收缩或替代方案确认任务。")
        suggestions.append("请补充“确认范围收缩与替代方案边界”任务。")

    deferred = [str(item) for item in (assumption_pack.get("deferred_scope", []) or [])]
    leaked = [item for item in deferred if item and item in task_text]
    if leaked:
        issues.append("已后置范围仍出现在MVP任务中。")
        issues.extend(leaked[:5])

    if not issues:
        return None
    return {
        "passed": False,
        "issues": ["受控假设审核未通过："] + issues,
        "suggestions": suggestions or ["请补齐假设验证、风险控制与上线前确认任务。"],
    }


def _build_prompt_quality_review(tasks: list[dict], prompts: list[dict]) -> dict | None:
    task_by_title = {
        str(task.get("title", "")).strip(): task for task in (tasks or []) if task.get("title")
    }
    fallback_p0: list[str] = []
    for prompt in prompts or []:
        if not prompt.get("is_fallback"):
            continue
        title = str(prompt.get("task_title", "")).strip()
        task = task_by_title.get(title, {})
        priority = str(task.get("priority", "")).strip().upper()
        if priority in {"P0", "最高", "高"}:
            fallback_p0.append(title or "未命名任务")

    if not fallback_p0:
        return None
    return {
        "passed": False,
        "issues": [
            "P0任务使用了兜底提示词，关键任务缺少针对性编码与测试说明。"
        ]
        + fallback_p0[:5],
        "suggestions": [
            "请重新生成这些P0任务的prompt_pack，确保包含输入输出、约束、边界条件、回归测试与验收标准。"
        ],
    }


def _build_reviewer_cache_payload(
    req: dict,
    fea: dict,
    arch: dict,
    tasks: list[dict],
    prompts: list[dict],
    previous_review: dict,
    review_rounds: int,
) -> dict:
    compact_tasks = [
        {
            "title": str(item.get("title", "")).strip(),
            "priority": str(item.get("priority", "")).strip(),
            "depends_on": [str(dep).strip() for dep in (item.get("depends_on", []) or [])],
        }
        for item in (tasks or [])
    ]
    compact_prompts = [
        {
            "task_title": str(item.get("task_title", "")).strip(),
            "coding_prompt": str(item.get("coding_prompt", "")).strip(),
            "test_prompt": str(item.get("test_prompt", "")).strip(),
        }
        for item in (prompts or [])
    ]
    return {
        "review_rounds": int(review_rounds),
        "requirement": {
            "summary": req.get("summary", ""),
            "constraints": req.get("constraints", []) or [],
        },
        "feasibility": {
            "feasible": fea.get("feasible"),
            "complexity": fea.get("complexity", ""),
            "risks": fea.get("risks", []) or [],
        },
        "architecture": {
            "style": arch.get("architecture_style", ""),
            "backend": arch.get("backend", []) or [],
            "frontend": arch.get("frontend", []) or [],
        },
        "tasks": compact_tasks,
        "prompts": compact_prompts,
        "previous_review": {
            "passed": bool(previous_review.get("passed")) if isinstance(previous_review, dict) else None,
            "issues": (previous_review.get("issues", []) if isinstance(previous_review, dict) else []) or [],
            "suggestions": (previous_review.get("suggestions", []) if isinstance(previous_review, dict) else []) or [],
        },
    }


def reviewer_node(state: ProjectState) -> ProjectState:
    req = state["requirement_doc"]
    fea = state["feasibility_report"]
    arch = state["architecture_plan"]
    tasks = state.get("task_breakdown", [])
    prompts = state.get("prompt_pack", [])
    review_rounds = int(state.get("review_rounds", 0) or 0)
    max_review_rounds = int(state.get("max_review_rounds", settings.review_max_rounds))
    previous_review = state.get("review_report", {}) or {}

    assumption_review = _build_assumption_pack_review(
        state.get("assumption_pack", {}),
        tasks,
    )
    if assumption_review is not None:
        return _apply_review_outcome(state, assumption_review, passed=False)

    prompt_quality_review = _build_prompt_quality_review(tasks, prompts)
    if prompt_quality_review is not None:
        return _apply_review_outcome(state, prompt_quality_review, passed=False)

    # Gate before reviewer LLM call:
    # key blocking issues from previous review must be covered by current tasks.
    is_rework_round = review_rounds > 0 and not bool(previous_review.get("passed"))
    if is_rework_round and (review_rounds + 1) >= max_review_rounds:
        conditional_pass = _build_conditional_pass_if_possible(state, previous_review)
        if conditional_pass is not None:
            return {
                **state,
                "review_report": conditional_pass,
                "review_rounds": review_rounds + 1,
                "next_step": "finish",
            }

    if is_rework_round:
        blocking_issues = extract_blocking_issues(previous_review, max_items=8)
        coverage_analysis = analyze_blocking_issue_coverage(
            tasks,
            blocking_issues,
            prompt_pack=prompts,
            min_evidence_hits=settings.coverage_min_evidence_hits,
            min_confidence=settings.coverage_min_confidence,
            blocking_confidence=settings.coverage_blocking_confidence,
        )
        uncovered = [str(item) for item in (coverage_analysis.get("uncovered", []) or [])]
        downgraded = [str(item) for item in (coverage_analysis.get("downgraded", []) or [])]
        timing_uncovered = [item for item in uncovered if _issue_is_research_timing_dispute(item, tasks)]
        if timing_uncovered:
            uncovered = [item for item in uncovered if item not in timing_uncovered]
            downgraded.extend(timing_uncovered)
            timing_diag = [
                {
                    "issue_text": item,
                    "issue_type": "dependency_timing",
                    "decision": "downgraded_research_timing_dispute",
                    "reason": "research_task_can_be_preflight_with_empty_depends_on",
                }
                for item in timing_uncovered
            ]
            coverage_analysis["diagnostics"] = (
                coverage_analysis.get("diagnostics", []) or []
            ) + timing_diag
        dependency_check = detect_dependency_cycles(tasks)
        if not dependency_check.get("has_cycle"):
            cycle_uncovered = [item for item in uncovered if _is_dependency_cycle_issue_text(item)]
            if cycle_uncovered:
                uncovered = [item for item in uncovered if item not in cycle_uncovered]
                downgraded.extend(cycle_uncovered)
                extra_diag = [
                    {
                        "issue_text": item,
                        "issue_type": "dependency_cycle",
                        "decision": "downgraded_no_cycle",
                        "has_cycle": False,
                    }
                    for item in cycle_uncovered
                ]
                coverage_analysis["diagnostics"] = (
                    coverage_analysis.get("diagnostics", []) or []
                ) + extra_diag
        if uncovered:
            suggestions = [
                "请先补齐上述阻塞项对应任务，再进入评审。",
                "建议在任务标题中显式包含阻塞项关键词，并补充依赖关系与验收标准。",
            ]
            if downgraded:
                suggestions.append(
                    "以下问题因证据置信度不足已降级为建议，请结合diagnostics复核："
                    + "；".join(downgraded[:3])
                )
            review_report = {
                "passed": False,
                "issues": [
                    "回流覆盖检查未通过：以下关键阻塞项尚未被任务清单命中。"
                ]
                + uncovered,
                "suggestions": suggestions,
                "diagnostics": coverage_analysis.get("diagnostics", []),
            }
            return _apply_review_outcome(state, review_report, passed=False)

    project_id = str(state.get("project_id", "") or state.get("thread_id", "") or "unknown")
    cache_payload = _build_reviewer_cache_payload(
        req=req,
        fea=fea,
        arch=arch,
        tasks=tasks,
        prompts=prompts,
        previous_review=previous_review,
        review_rounds=review_rounds,
    )
    cached_review = load_cached_review(project_id, cache_payload)
    if cached_review is not None:
        cached_review, passed = _postprocess_review_report_with_evidence(
            tasks=tasks,
            prompts=prompts,
            review_report=cached_review,
        )
        cached_review, passed = _normalize_review_passed(cached_review)
        return _apply_review_outcome(
            state,
            review_report=cached_review,
            passed=passed,
        )

    compact_context = (
        "请对当前方案进行评审，重点检查遗漏、冲突、不可实施风险与范围过大问题。\n"
        "严格规则：请仅基于提供的task_breakdown.depends_on判断依赖与循环，不要臆造依赖边。\n"
        "若你认为某任务应调整依赖或执行时机，请写入suggestions，不要作为阻塞issues。\n"
        "对技术预研/兼容性验证/POC类任务，允许前置执行（depends_on为空并不自动构成阻塞）。\n"
        f"需求摘要: {req.get('summary', '')}\n"
        f"关键约束: {summarize_key_list(req.get('constraints', []), max_items=10, max_chars=1200)}\n"
        f"可行性: feasible={fea.get('feasible')} complexity={fea.get('complexity')}\n"
        f"主要风险: {summarize_key_list(fea.get('risks', []), max_items=8, max_chars=1200)}\n"
        f"架构风格: {arch.get('architecture_style', '')}\n"
        f"后端: {summarize_key_list(arch.get('backend', []), max_items=8, max_chars=600)}\n"
        f"前端: {summarize_key_list(arch.get('frontend', []), max_items=8, max_chars=600)}\n"
        f"任务总数: {len(tasks)}\n"
        f"任务摘要:\n{summarize_task_breakdown(tasks, max_items=12)}\n"
        f"提示词总数: {len(prompts)}\n"
        f"提示词摘要:\n{summarize_prompt_pack(prompts, max_items=8)}"
    )
    if is_rework_round:
        compact_context += (
            "\n回流阻塞项摘要:\n"
            f"{summarize_review_feedback(previous_review, max_issues=6, max_suggestions=4)}"
        )

    agent = build_reviewer_agent()
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": compact_context,
                }
            ]
        }
    )
    structured = extract_structured_response(result)
    review_report, passed = _postprocess_review_report_with_evidence(
        tasks=tasks,
        prompts=prompts,
        review_report=structured.model_dump(),
    )
    review_report, passed = _normalize_review_passed(review_report)
    save_cached_review(project_id, cache_payload, review_report)
    return _apply_review_outcome(state, review_report, passed=passed)
