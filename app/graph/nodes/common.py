import json
import re
from typing import Any
from difflib import SequenceMatcher


def extract_structured_response(result: dict):
    structured = result.get("structured_response")
    if structured is None:
        raise ValueError("Agent did not return structured_response")
    return structured


def compact_json(data: Any, max_chars: int = 3000) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "...(truncated)"


def summarize_task_breakdown(tasks: list[dict[str, Any]], max_items: int = 12) -> str:
    lines = []
    for item in tasks[:max_items]:
        title = item.get("title", "")
        priority = item.get("priority", "")
        owner = item.get("owner_role", "")
        deps = item.get("depends_on", [])
        dep_titles = ", ".join([str(dep) for dep in deps[:2]]) if deps else "-"
        lines.append(
            f"- {title} | priority={priority} | owner={owner} | deps={len(deps)} | dep_titles={dep_titles}"
        )
    if len(tasks) > max_items:
        lines.append(f"... and {len(tasks) - max_items} more tasks")
    return "\n".join(lines)


def summarize_prompt_pack(prompt_pack: list[dict[str, Any]], max_items: int = 8) -> str:
    lines = []
    for item in prompt_pack[:max_items]:
        task_title = item.get("task_title", "")
        coding_prompt = item.get("coding_prompt", "")
        test_prompt = item.get("test_prompt", "")
        lines.append(
            f"- {task_title} | coding_len={len(coding_prompt)} | test_len={len(test_prompt)}"
        )
    if len(prompt_pack) > max_items:
        lines.append(f"... and {len(prompt_pack) - max_items} more prompt items")
    return "\n".join(lines)


def summarize_review_feedback(
    review_report: dict[str, Any],
    max_issues: int = 8,
    max_suggestions: int = 8,
) -> str:
    issues = review_report.get("issues", []) if isinstance(review_report, dict) else []
    suggestions = (
        review_report.get("suggestions", []) if isinstance(review_report, dict) else []
    )
    lines: list[str] = []
    if issues:
        lines.append("评审问题(issues):")
        for item in issues[:max_issues]:
            lines.append(f"- {item}")
        if len(issues) > max_issues:
            lines.append(f"... and {len(issues) - max_issues} more issues")
    if suggestions:
        lines.append("评审建议(suggestions):")
        for item in suggestions[:max_suggestions]:
            lines.append(f"- {item}")
        if len(suggestions) > max_suggestions:
            lines.append(f"... and {len(suggestions) - max_suggestions} more suggestions")
    return "\n".join(lines)


def summarize_key_list(items: list[Any], max_items: int = 8, max_chars: int = 1200) -> str:
    compact_items = [str(item) for item in (items or [])[:max_items]]
    return compact_json(compact_items, max_chars=max_chars)


def extract_blocking_issues(review_report: dict[str, Any], max_items: int = 8) -> list[str]:
    if not isinstance(review_report, dict):
        return []
    issues = [str(i) for i in (review_report.get("issues", []) or [])]
    if not issues:
        return []

    blocking_markers = [
        "关键",
        "缺失",
        "阻塞",
        "无法",
        "失败",
        "风险",
        "未覆盖",
        "must",
        "blocker",
        "critical",
        "missing",
        "cannot",
        "failed",
        "risk",
        "uncovered",
    ]
    selected = [i for i in issues if any(m in i for m in blocking_markers)]
    if not selected:
        selected = issues
    return selected[:max_items]


def _normalize_text(text: str) -> str:
    text = re.sub(r"^【[^】]+】", "", text).strip()
    text = text.replace("（", "(").replace("）", ")")
    return text


def _extract_issue_focus_phrase(issue: str) -> str | None:
    patterns = [
        r"【[^】\-]{0,40}-([^】]{2,80})】",
        r"缺少([^，。；\n]{2,80})任务",
        r"缺少([^，。；\n]{2,120})(?:。|，|；|$)",
        r"未包含([^，。；\n]{2,80})任务",
        r"新增任务[:：]\s*([^，。；\n]{2,80})",
        r"需求明确要求['‘“\"]([^'’”\"]{2,80})['’”\"]功能",
        r"未见([^，。；\n]{2,80})相关任务",
        r"未见([^，。；\n]{2,80})开发任务",
        r"未明确包含([^，。；\n]{2,80})逻辑",
        r"([^，。；\n]{2,80})未确定",
        r"missing\s+([^,.;\n]{2,120})",
        r"not\s+found\s+([^,.;\n]{2,120})",
        r"lack(?:s|ing)?\s+([^,.;\n]{2,120})",
        r"failed to include\s+([^,.;\n]{2,120})",
        r"require(?:ment)?\s+(?:explicitly\s+)?requires?\s+['\"“”]([^'\"“”]{2,120})['\"“”]",
        r"no\s+([^,.;\n]{2,120})\s+task",
        r"without\s+([^,.;\n]{2,120})",
    ]
    text = _normalize_text(issue)
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            phrase = _normalize_text(m.group(1))
            phrase = re.sub(r"^的", "", phrase).strip()
            phrase = phrase.strip("'\"‘’“”`")
            phrase = re.sub(r"[（(].*?[)）]$", "", phrase).strip()
            phrase = re.sub(r"(相关任务|开发任务|任务)$", "", phrase).strip()
            return phrase if phrase else None
    return None


def _extract_issue_terms(issue: str, max_terms: int = 4) -> list[str]:
    text = _normalize_text(issue)
    tokens = re.findall(r"[A-Za-z0-9_\-]{3,}|[\u4e00-\u9fff]{2,}", text)
    stop_words = {
        "关键功能",
        "缺失",
        "任务清单",
        "任务",
        "功能",
        "机制",
        "方案",
        "实现",
        "支持",
        "导致",
        "影响",
        "当前",
        "系统",
        "流程",
        "上线",
    }
    terms: list[str] = []
    for token in tokens:
        token = _normalize_term(token)
        if not token:
            continue
        if token in stop_words:
            continue
        if token in _NOISE_TERMS:
            continue
        if any(noise in token for noise in _NOISE_TERMS):
            continue
        if token not in terms:
            terms.append(token)
        if len(terms) >= max_terms:
            break
    return terms


def _tokenize_text(text: str) -> list[str]:
    raw_tokens = re.findall(r"[A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}", _normalize_text(text))
    tokens: list[str] = []
    for item in raw_tokens:
        normalized = _normalize_term(item)
        if not normalized:
            continue
        tokens.append(normalized)
        if len(normalized) >= 4:
            for cluster_terms in _META_CAPABILITY_CLUSTERS.values():
                for term in cluster_terms:
                    term_norm = _normalize_term(term)
                    if len(term_norm) >= 2 and term_norm in normalized and term_norm != normalized:
                        tokens.append(term_norm)
    return tokens


_ACTION_MARKERS: tuple[str, ...] = (
    "开发",
    "实现",
    "设计",
    "新增",
    "删除",
    "更新",
    "查看",
    "取消",
    "提交",
    "审批",
    "导入",
    "导出",
    "处理",
    "校验",
    "联调",
    "配置",
    "通知",
    "释放",
    "同步",
    "查询",
    "build",
    "implement",
    "design",
    "add",
    "remove",
    "update",
    "view",
    "cancel",
    "submit",
    "approve",
    "import",
    "export",
    "process",
    "validate",
    "integrate",
    "configure",
    "notify",
    "release",
    "sync",
    "query",
)

_CLUSTER_STOP_WORDS: set[str] = {
    "任务",
    "功能",
    "相关",
    "开发",
    "实现",
    "方案",
    "问题",
    "风险",
    "流程",
    "系统",
    "页面",
    "接口",
    "逻辑",
}

_NOISE_TERMS: set[str] = {
    "需求明确要求",
    "任务列表中未见",
    "任务列表中未发现",
    "任务清单中缺少",
    "关键需求遗漏",
    "功能缺失",
    "默认",
    "超期",
    "自动",
    "requirement explicitly requires",
    "not found in task list",
    "missing from task list",
    "key requirement missing",
    "feature missing",
    "default",
    "automatic",
}

_TERM_NORMALIZATION_PAIRS: tuple[tuple[str, str], ...] = (
    ("压测", "性能验证"),
    ("基准测试", "性能验证"),
    ("性能基准", "性能验证"),
    ("性能测试", "性能验证"),
    ("压测验证", "性能验证"),
    ("核验", "验证"),
    ("校验", "验证"),
    ("校核", "验证"),
    ("归档", "留存"),
    ("保留", "留存"),
    ("留档", "留存"),
    ("清理", "回收"),
    ("删除", "回收"),
    ("回收", "回收"),
    ("报警", "告警"),
    ("预警", "告警"),
    ("鉴权", "认证"),
    ("授权", "认证"),
    ("认证授权", "认证"),
    ("退化", "降级"),
    ("回退", "回滚"),
    ("回补", "补偿"),
    ("补救", "补偿"),
    ("去重", "幂等"),
    ("防重", "幂等"),
    ("串联", "联调"),
    ("对接", "联调"),
    ("追踪", "链路"),
)

_META_CAPABILITY_CLUSTERS: dict[str, tuple[str, ...]] = {
    "delivery": (
        "前端",
        "后端",
        "联调",
        "页面",
        "接口",
        "交付",
        "端到端",
        "frontend",
        "backend",
        "integration",
        "page",
        "api",
        "delivery",
        "e2e",
    ),
    "data_integrity": (
        "幂等",
        "一致性",
        "状态机",
        "事务",
        "锁",
        "回滚",
        "补偿",
        "idempotent",
        "consistency",
        "state machine",
        "transaction",
        "rollback",
        "compensation",
        "lock",
    ),
    "performance": (
        "性能",
        "延迟",
        "容量",
        "压测",
        "吞吐",
        "负载",
        "超时",
        "performance",
        "latency",
        "capacity",
        "stress",
        "throughput",
        "load",
        "timeout",
        "qps",
        "p95",
        "p99",
    ),
    "security": (
        "权限",
        "鉴权",
        "认证",
        "隔离",
        "审计",
        "合规",
        "越权",
        "security",
        "auth",
        "authentication",
        "authorization",
        "isolation",
        "audit",
        "compliance",
        "access control",
    ),
    "observability": (
        "监控",
        "日志",
        "告警",
        "指标",
        "追踪",
        "链路",
        "monitoring",
        "log",
        "alert",
        "metrics",
        "tracing",
        "trace",
    ),
    "release_safety": ("灰度", "发布", "回滚", "变更", "演练", "release", "rollback", "change", "drill"),
}

_DYNAMIC_CLUSTER_WEIGHT = 0.12
_META_CLUSTER_WEIGHT = 0.08


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _token_overlap_f1(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter <= 0:
        return 0.0
    precision = inter / max(1, len(a))
    recall = inter / max(1, len(b))
    denom = precision + recall
    if denom <= 0:
        return 0.0
    return (2 * precision * recall) / denom


def _normalize_term(term: str) -> str:
    normalized = str(term or "").strip().lower()
    if not normalized:
        return ""
    for src, dst in _TERM_NORMALIZATION_PAIRS:
        if src in normalized:
            normalized = normalized.replace(src, dst)
    return normalized


def _sequence_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _detect_language_profile(text: str) -> str:
    s = str(text or "")
    zh_count = len(re.findall(r"[\u4e00-\u9fff]", s))
    en_count = len(re.findall(r"[A-Za-z]", s))
    if zh_count > 0 and en_count > 0:
        return "mixed"
    if zh_count > 0:
        return "zh"
    if en_count > 0:
        return "en"
    return "other"


def _extract_action_object_pairs(text: str) -> set[tuple[str, str]]:
    normalized = _normalize_text(text)
    pairs: set[tuple[str, str]] = set()
    for action in _ACTION_MARKERS:
        pattern = rf"{action}([\u4e00-\u9fffA-Za-z0-9_\-]{{2,20}})"
        for match in re.findall(pattern, normalized):
            obj = str(match).strip()
            if obj:
                pairs.add((action, obj))
    return pairs


def _structure_overlap_score(
    issue_pairs: set[tuple[str, str]], source_pairs: set[tuple[str, str]]
) -> float:
    if not issue_pairs or not source_pairs:
        return 0.0
    hit = 0
    for ia, io in issue_pairs:
        for sa, so in source_pairs:
            if ia != sa:
                continue
            if io == so or io in so or so in io:
                hit += 1
                break
    return hit / max(1, len(issue_pairs))


def _build_dynamic_clusters(texts: list[str], top_k: int = 8) -> dict[str, set[str]]:
    token_lists: list[list[str]] = []
    doc_freq: dict[str, int] = {}
    for text in texts:
        tokens = [tok for tok in _tokenize_text(text) if tok not in _CLUSTER_STOP_WORDS]
        if not tokens:
            continue
        token_lists.append(tokens)
        for token in set(tokens):
            doc_freq[token] = doc_freq.get(token, 0) + 1

    if not token_lists or not doc_freq:
        return {}

    top_terms = sorted(doc_freq.keys(), key=lambda t: (-doc_freq[t], t))[: max(1, top_k)]
    clusters: dict[str, set[str]] = {}
    for center in top_terms:
        co_freq: dict[str, int] = {}
        for tokens in token_lists:
            token_set = set(tokens)
            if center not in token_set:
                continue
            for token in token_set:
                if token == center or token in _CLUSTER_STOP_WORDS:
                    continue
                co_freq[token] = co_freq.get(token, 0) + 1
        cluster_terms = [center] + [
            token
            for token, _ in sorted(co_freq.items(), key=lambda kv: (-kv[1], kv[0]))[:4]
        ]
        clusters[center] = set(cluster_terms)
    return clusters


def _merge_clusters(
    base: dict[str, set[str]],
    extra: dict[str, set[str]],
    *,
    max_terms_per_cluster: int = 8,
) -> dict[str, set[str]]:
    merged: dict[str, set[str]] = {k: set(v) for k, v in (base or {}).items()}
    for center, terms in (extra or {}).items():
        if center not in merged:
            merged[center] = set(terms)
        else:
            merged[center].update(set(terms))
        if len(merged[center]) > max_terms_per_cluster:
            merged[center] = set(sorted(merged[center])[:max_terms_per_cluster])
    return merged


def _build_project_dynamic_clusters_from_memory(
    term_cluster_memory: dict[str, Any] | None,
) -> dict[str, set[str]]:
    memory = term_cluster_memory or {}
    pairs = memory.get("cooccurrence", {}) if isinstance(memory, dict) else {}
    if not isinstance(pairs, dict) or not pairs:
        return {}
    clusters: dict[str, set[str]] = {}
    # pair key format: "a||b"
    adjacency: dict[str, dict[str, int]] = {}
    for key, value in pairs.items():
        if not isinstance(key, str) or "||" not in key:
            continue
        a, b = key.split("||", 1)
        a = _normalize_term(a)
        b = _normalize_term(b)
        if not a or not b:
            continue
        score = int(value or 0)
        if score <= 0:
            continue
        adjacency.setdefault(a, {})[b] = adjacency.setdefault(a, {}).get(b, 0) + score
        adjacency.setdefault(b, {})[a] = adjacency.setdefault(b, {}).get(a, 0) + score

    for center, neighbors in adjacency.items():
        ranked = sorted(neighbors.items(), key=lambda kv: (-kv[1], kv[0]))
        selected = [term for term, score in ranked if score >= 2][:4]
        if selected:
            clusters[center] = {center, *selected}
    return clusters


def _update_term_cluster_memory(
    term_cluster_memory: dict[str, Any] | None,
    tasks: list[dict[str, Any]],
    prompt_pack: list[dict[str, Any]] | None,
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    memory = dict(term_cluster_memory or {})
    co = memory.get("cooccurrence", {})
    if not isinstance(co, dict):
        co = {}

    source_text = " ".join(
        [
            " ".join(
                [
                    str(item.get("title", "")),
                    str(item.get("description", "")),
                    " ".join(str(dep) for dep in (item.get("depends_on", []) or [])),
                ]
            )
            for item in (tasks or [])
        ]
        + [
            " ".join(
                [
                    str(item.get("task_title", "")),
                    str(item.get("coding_prompt", "")),
                    str(item.get("test_prompt", "")),
                ]
            )
            for item in (prompt_pack or [])
        ]
    )
    source_tokens = [tok for tok in _tokenize_text(source_text) if len(tok) >= 2]
    source_token_set = set(source_tokens)

    for item in diagnostics or []:
        if not isinstance(item, dict):
            continue
        decision = str(item.get("decision", ""))
        # Learn primarily from successful/soft-successful coverage outcomes.
        if decision not in {"covered", "downgraded_uncovered"}:
            continue
        terms = [str(t) for t in (item.get("issue_terms", []) or []) if str(t).strip()]
        normalized_terms = [_normalize_term(t) for t in terms]
        normalized_terms = [t for t in normalized_terms if t and t in source_token_set]
        uniq_terms = list(dict.fromkeys(normalized_terms))[:10]
        for i in range(len(uniq_terms)):
            for j in range(i + 1, len(uniq_terms)):
                a, b = sorted([uniq_terms[i], uniq_terms[j]])
                key = f"{a}||{b}"
                co[key] = int(co.get(key, 0)) + 1

    memory["cooccurrence"] = co
    return memory


def _cluster_overlap_score(
    target_tokens: set[str],
    source_tokens: set[str],
    clusters: dict[str, set[str]],
) -> tuple[float, list[str]]:
    if not target_tokens or not source_tokens or not clusters:
        return 0.0, []
    matched_clusters: list[str] = []
    scores: list[float] = []
    for center, terms in clusters.items():
        if not (terms & target_tokens):
            continue
        overlap = terms & source_tokens
        if not overlap:
            continue
        matched_clusters.append(center)
        scores.append(len(overlap) / max(1, len(terms)))
    if not scores:
        return 0.0, []
    return round(sum(scores) / len(scores), 3), matched_clusters[:5]


def _extract_issue_focus(issue: str) -> tuple[str, float]:
    phrase = _extract_issue_focus_phrase(issue)
    if phrase:
        return phrase, 0.9

    terms = _extract_issue_terms(issue, max_terms=3)
    if terms:
        return " ".join(terms[:2]), 0.6
    return "", 0.4


def _extract_quoted_requirements(issue: str, max_items: int = 3) -> list[str]:
    text = _normalize_text(issue)
    matches = re.findall(r"['‘“\"]([^'’”\"]{2,120})['’”\"]", text)
    requirements: list[str] = []
    for item in matches:
        normalized = _normalize_text(str(item))
        if not normalized:
            continue
        if normalized not in requirements:
            requirements.append(normalized)
        if len(requirements) >= max_items:
            break
    return requirements


def _build_evidence_sources(
    tasks: list[dict[str, Any]],
    prompt_pack: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    task_titles = " ".join(str(item.get("title", "")) for item in (tasks or []))
    task_descriptions = " ".join(
        str(item.get("description", "")) for item in (tasks or [])
    )
    depends_on = " ".join(
        " ".join(str(dep) for dep in (item.get("depends_on", []) or []))
        for item in (tasks or [])
    )
    prompts = prompt_pack or []
    prompt_task_titles = " ".join(str(item.get("task_title", "")) for item in prompts)
    prompt_content = " ".join(
        f"{item.get('coding_prompt', '')} {item.get('test_prompt', '')}" for item in prompts
    )
    return {
        "task_title": _normalize_text(task_titles),
        "task_description": _normalize_text(task_descriptions),
        "prompt_task_title": _normalize_text(prompt_task_titles),
        "prompt_content": _normalize_text(prompt_content),
        "depends_on": _normalize_text(depends_on),
    }


def _source_hit(
    capability: str,
    issue_terms: list[str],
    source_text: str,
    dynamic_clusters: dict[str, set[str]] | None = None,
    meta_clusters: dict[str, set[str]] | None = None,
) -> tuple[bool, float, dict[str, float]]:
    if not source_text:
        return False, 0.0, {"keyword": 0.0, "semantic": 0.0, "structure": 0.0}

    source_tokens = set(_tokenize_text(source_text))
    issue_token_set = set(issue_terms)
    capability_tokens = set(_tokenize_text(capability))

    keyword_terms = capability_tokens | issue_token_set
    keyword_hits = sum(1 for term in keyword_terms if term in source_tokens)
    keyword_score = (
        keyword_hits / max(1, len(keyword_terms))
        if keyword_terms
        else 0.0
    )
    direct_capability_match = bool(capability and capability in source_text)
    if direct_capability_match:
        keyword_score = max(keyword_score, 1.0)

    semantic_token_score = _jaccard_similarity(keyword_terms, source_tokens)
    semantic_f1_score = _token_overlap_f1(keyword_terms, source_tokens)
    semantic_char_score = _sequence_similarity(capability or " ".join(issue_terms[:3]), source_text)
    semantic_score = max(semantic_token_score, semantic_f1_score, semantic_char_score)
    if direct_capability_match:
        semantic_score = max(semantic_score, 0.9)

    issue_pairs = _extract_action_object_pairs(capability + " " + " ".join(issue_terms))
    source_pairs = _extract_action_object_pairs(source_text)
    structure_score = _structure_overlap_score(issue_pairs, source_pairs)

    dynamic_score, _ = _cluster_overlap_score(
        keyword_terms,
        source_tokens,
        dynamic_clusters or {},
    )
    meta_score, _ = _cluster_overlap_score(
        keyword_terms,
        source_tokens,
        meta_clusters or {},
    )

    score = (
        0.45 * keyword_score
        + 0.35 * semantic_score
        + 0.20 * structure_score
        + (_DYNAMIC_CLUSTER_WEIGHT * dynamic_score)
        + (_META_CLUSTER_WEIGHT * meta_score)
    )
    hit_threshold = 0.55
    if direct_capability_match or keyword_score >= 0.5:
        hit_threshold = 0.42
    is_hit = score >= hit_threshold
    components = {
        "keyword": round(keyword_score, 3),
        "semantic": round(semantic_score, 3),
        "structure": round(structure_score, 3),
        "dynamic_cluster": round(dynamic_score, 3),
        "meta_cluster": round(meta_score, 3),
    }
    return is_hit, round(score, 3), components


def analyze_blocking_issue_coverage(
    tasks: list[dict[str, Any]],
    blocking_issues: list[str],
    *,
    prompt_pack: list[dict[str, Any]] | None = None,
    min_evidence_hits: int = 2,
    min_confidence: float = 0.65,
    blocking_confidence: float = 0.75,
    term_cluster_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sources = _build_evidence_sources(tasks, prompt_pack=prompt_pack)
    source_texts = [str(v) for v in sources.values() if str(v).strip()]
    dynamic_clusters = _build_dynamic_clusters(source_texts, top_k=8)
    learned_clusters = _build_project_dynamic_clusters_from_memory(term_cluster_memory)
    dynamic_clusters = _merge_clusters(dynamic_clusters, learned_clusters, max_terms_per_cluster=8)
    meta_clusters = {k: set(v) for k, v in _META_CAPABILITY_CLUSTERS.items()}
    source_weights = {
        "task_title": 0.30,
        "task_description": 0.22,
        "prompt_task_title": 0.20,
        "prompt_content": 0.18,
        "depends_on": 0.10,
    }

    uncovered: list[str] = []
    downgraded: list[str] = []
    diagnostics: list[dict[str, Any]] = []

    for issue in blocking_issues:
        issue_text = str(issue)
        capability, parse_confidence = _extract_issue_focus(issue_text)
        issue_terms = _extract_issue_terms(issue_text, max_terms=5)
        if capability:
            issue_terms = list(dict.fromkeys(_tokenize_text(capability) + issue_terms))

        matched_sources: list[str] = []
        source_scores: dict[str, float] = {}
        source_components: dict[str, dict[str, float]] = {}
        soft_source_hits = 0
        for source_name, source_text in sources.items():
            is_hit, score, components = _source_hit(
                capability,
                issue_terms,
                source_text,
                dynamic_clusters=dynamic_clusters,
                meta_clusters=meta_clusters,
            )
            source_scores[source_name] = score
            source_components[source_name] = components
            if is_hit:
                matched_sources.append(source_name)
            if score >= 0.35:
                soft_source_hits += 1

        evidence_hits = len(matched_sources)
        source_support = sum(source_weights.get(name, 0.0) for name in matched_sources)
        avg_match_quality = (
            sum(source_scores.get(name, 0.0) for name in matched_sources) / evidence_hits
            if evidence_hits
            else 0.0
        )
        # confidence combines:
        # - cross-source support breadth (how many weighted sources hit)
        # - average quality on matched sources
        coverage_confidence = (0.65 * source_support) + (0.35 * avg_match_quality)
        effective_evidence_hits = evidence_hits

        medium_source_hits = sum(1 for score in source_scores.values() if float(score) >= 0.40)
        max_source_score = max(source_scores.values()) if source_scores else 0.0
        max_keyword_score = 0.0
        for comp in source_components.values():
            if isinstance(comp, dict):
                max_keyword_score = max(max_keyword_score, float(comp.get("keyword", 0.0) or 0.0))
        source_token_set = set(_tokenize_text(" ".join(source_texts)))
        issue_term_hit_count = len(set(issue_terms) & source_token_set)
        if issue_term_hit_count >= 2 and soft_source_hits > 0:
            effective_evidence_hits += 1
        is_covered = (
            effective_evidence_hits >= max(1, int(min_evidence_hits))
            and coverage_confidence >= float(min_confidence)
        )
        source_joined_text = " ".join(source_texts)
        missing_claim_markers = ("未见", "未发现", "缺少", "遗漏")
        missing_capability_hits = 0
        if capability and any(marker in issue_text for marker in missing_claim_markers):
            parts = re.split(r"[、,，/\\+\s]+", capability)
            key_parts = [str(p).strip() for p in parts if str(p).strip() and len(str(p).strip()) >= 2]
            seen_parts: set[str] = set()
            for part in key_parts:
                if part in seen_parts:
                    continue
                seen_parts.add(part)
                if part in source_joined_text:
                    missing_capability_hits += 1
        quoted_requirement_hits = 0
        for quoted_req in _extract_quoted_requirements(issue_text, max_items=3):
            req_tokens = [tok for tok in _tokenize_text(quoted_req) if len(tok) >= 2]
            if not req_tokens:
                continue
            token_hits = sum(1 for tok in set(req_tokens) if tok in source_joined_text)
            if token_hits >= max(2, min(3, len(set(req_tokens)))):
                quoted_requirement_hits += 1
        issue_term_phrase_hits = 0
        seen_issue_terms: set[str] = set()
        for term in issue_terms:
            t = str(term).strip()
            if not t or t in seen_issue_terms:
                continue
            seen_issue_terms.add(t)
            if len(t) < 2:
                continue
            if t in source_joined_text:
                issue_term_phrase_hits += 1
        weak_covered = (
            not is_covered
            and max_source_score >= 0.45
            and medium_source_hits >= 2
            and issue_term_hit_count >= 2
        )
        borderline_semantic_cover = (
            not is_covered
            and issue_term_hit_count >= 2
            and max_source_score >= 0.30
            and max_keyword_score >= 0.14
        )
        missing_claim_phrase_cover = (
            not is_covered
            and any(marker in issue_text for marker in missing_claim_markers)
            and (
                issue_term_hit_count >= 2
                or missing_capability_hits >= 2
                or issue_term_phrase_hits >= 2
                or quoted_requirement_hits >= 1
            )
        )
        if weak_covered or borderline_semantic_cover or missing_claim_phrase_cover:
            is_covered = True

        missing_confidence = parse_confidence * max(0.2, 1.0 - coverage_confidence)
        if is_covered:
            decision = "covered"
        elif missing_confidence >= float(blocking_confidence):
            decision = "blocking_uncovered"
            uncovered.append(issue_text)
        else:
            decision = "downgraded_uncovered"
            downgraded.append(issue_text)

        diagnostics.append(
            {
                "issue_text": issue_text,
                "language_profile": _detect_language_profile(issue_text),
                "missing_capability": capability,
                "issue_terms": issue_terms[:6],
                "evidence_checked": list(sources.keys()),
                "matched_evidence": matched_sources,
                "evidence_hits": evidence_hits,
                "effective_evidence_hits": int(effective_evidence_hits),
                "soft_source_hits": int(soft_source_hits),
                "source_support": round(source_support, 3),
                "avg_match_quality": round(avg_match_quality, 3),
                "coverage_confidence": round(coverage_confidence, 3),
                "missing_confidence": round(missing_confidence, 3),
                "source_scores": source_scores,
                "source_components": source_components,
                "cluster_weights": {
                    "dynamic": _DYNAMIC_CLUSTER_WEIGHT,
                    "meta": _META_CLUSTER_WEIGHT,
                },
                "dynamic_clusters_used": {
                    k: sorted(list(v)) for k, v in list(dynamic_clusters.items())[:8]
                },
                "meta_clusters_used": {
                    k: sorted(list(v)) for k, v in meta_clusters.items()
                },
                "is_blocking": decision == "blocking_uncovered",
                "decision": decision,
                "why_not_matched": ""
                if matched_sources
                else "no sufficient cross-source evidence",
                "weak_covered": weak_covered,
                "borderline_semantic_cover": borderline_semantic_cover,
                "missing_claim_phrase_cover": missing_claim_phrase_cover,
                "missing_capability_hits": int(missing_capability_hits),
                "quoted_requirement_hits": int(quoted_requirement_hits),
                "issue_term_phrase_hits": int(issue_term_phrase_hits),
                "medium_source_hits": medium_source_hits,
                "max_source_score": round(float(max_source_score), 3),
                "max_keyword_score": round(float(max_keyword_score), 3),
                "issue_term_hit_count": int(issue_term_hit_count),
            }
        )

    return {
        "uncovered": uncovered,
        "downgraded": downgraded,
        "diagnostics": diagnostics,
        "term_cluster_memory": _update_term_cluster_memory(
            term_cluster_memory,
            tasks,
            prompt_pack,
            diagnostics,
        ),
        "learned_clusters": {k: sorted(list(v)) for k, v in list(learned_clusters.items())[:16]},
    }


def detect_dependency_cycles(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    graph: dict[str, set[str]] = {}
    duplicate_titles: list[str] = []
    unknown_dependencies: set[str] = set()

    for task in tasks or []:
        title = str(task.get("title", "")).strip()
        if not title:
            continue
        if title in graph and title not in duplicate_titles:
            duplicate_titles.append(title)
        graph.setdefault(title, set())

    for task in tasks or []:
        title = str(task.get("title", "")).strip()
        if not title:
            continue
        for dep in (task.get("depends_on", []) or []):
            dep_title = str(dep).strip()
            if not dep_title:
                continue
            if dep_title not in graph:
                unknown_dependencies.add(dep_title)
                continue
            graph[title].add(dep_title)

    visited: dict[str, int] = {node: 0 for node in graph}
    stack: list[str] = []
    stack_index: dict[str, int] = {}
    cycles: list[list[str]] = []
    cycle_keys: set[tuple[str, ...]] = set()

    def _canonical_cycle(path: list[str]) -> tuple[str, ...]:
        ring = path[:-1] if len(path) > 1 and path[0] == path[-1] else list(path)
        if not ring:
            return tuple()
        rotations = [tuple(ring[i:] + ring[:i]) for i in range(len(ring))]
        return min(rotations)

    def _dfs(node: str) -> None:
        visited[node] = 1
        stack_index[node] = len(stack)
        stack.append(node)
        for dep in graph.get(node, set()):
            state = visited.get(dep, 0)
            if state == 0:
                _dfs(dep)
            elif state == 1:
                start = stack_index.get(dep, 0)
                cycle_path = stack[start:] + [dep]
                key = _canonical_cycle(cycle_path)
                if key and key not in cycle_keys:
                    cycle_keys.add(key)
                    cycles.append(cycle_path)
        stack.pop()
        stack_index.pop(node, None)
        visited[node] = 2

    for node in graph:
        if visited[node] == 0:
            _dfs(node)

    return {
        "has_cycle": bool(cycles),
        "cycles": cycles,
        "unknown_dependencies": sorted(unknown_dependencies),
        "duplicate_titles": duplicate_titles,
    }
