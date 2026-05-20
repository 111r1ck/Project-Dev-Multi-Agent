from pathlib import Path

import pytest

import app.mcp.codex_export_server as mcp_server
from app.mcp.codex_export_server import (
    _format_run_result,
    _generate_project_id,
    _build_state_summary,
    _list_project_export_files,
    _normalize_sections,
    _read_export_file,
    _section_value,
)


def test_normalize_sections_defaults_and_validation():
    all_sections = _normalize_sections(None)
    assert "summary" in all_sections
    picked = _normalize_sections(["tasks", "review"])
    assert picked == ["tasks", "review"]


def test_build_state_summary_counts():
    values = {
        "project_id": "demo-1",
        "task_breakdown": [{}, {}],
        "prompt_pack": [{}],
        "review_report": {
            "passed": True,
            "issues": ["i1"],
            "suggestions": ["s1", "s2"],
            "diagnostics": [{}, {}],
        },
    }
    summary = _build_state_summary(values)
    assert summary["project_id"] == "demo-1"
    assert summary["task_count"] == 2
    assert summary["prompt_count"] == 1
    assert summary["review_passed"] is True
    assert summary["issue_count"] == 1
    assert summary["suggestion_count"] == 2
    assert summary["diagnostics_count"] == 2


def test_section_value_maps_sections():
    values = {
        "project_id": "demo-2",
        "task_breakdown": [{"title": "t1"}],
        "prompt_pack": [{"task_title": "t1"}],
        "requirement_doc": {"summary": "x"},
        "feasibility_report": {"feasible": True},
        "architecture_plan": {"architecture_style": "mono"},
        "review_report": {"passed": True, "diagnostics": [{"issue_text": "i"}]},
    }
    assert _section_value(values, "summary")["project_id"] == "demo-2"
    assert _section_value(values, "tasks") == [{"title": "t1"}]
    assert _section_value(values, "prompts") == [{"task_title": "t1"}]
    assert _section_value(values, "diagnostics") == [{"issue_text": "i"}]


def test_list_project_export_files_sorted(tmp_path: Path):
    base = tmp_path / "exports" / "demo-3"
    base.mkdir(parents=True, exist_ok=True)
    f1 = base / "a.json"
    f2 = base / "b.json"
    f1.write_text("1", encoding="utf-8")
    f2.write_text("22", encoding="utf-8")
    files = _list_project_export_files("demo-3", base_dir=str(tmp_path / "exports"))
    assert len(files) == 2
    assert {item["name"] for item in files} == {"a.json", "b.json"}


def test_read_export_file_reads_text(tmp_path: Path):
    base = tmp_path / "exports" / "demo-4"
    base.mkdir(parents=True, exist_ok=True)
    f1 = base / "demo.md"
    f1.write_text("# x\nok", encoding="utf-8")
    data = _read_export_file("demo-4", "demo.md", base_dir=str(tmp_path / "exports"))
    assert data["name"] == "demo.md"
    assert "ok" in data["content"]


def test_generate_project_id_has_prefix():
    pid = _generate_project_id("demo")
    assert pid.startswith("demo-")
    assert len(pid.split("-")) >= 3


def test_format_run_result_interrupted_and_completed():
    interrupted = _format_run_result("p1", {"__interrupt__": [{"x": 1}]})
    assert interrupted["status"] == "interrupted"
    completed = _format_run_result("p1", {"a": 1})
    assert completed["status"] == "completed"


class _FakeTask:
    def __init__(self, interrupts):
        self.interrupts = interrupts


class _FakeSnapshot:
    def __init__(self, *, values=None, next_nodes=None, tasks=None):
        self.values = values or {}
        self.next = tuple(next_nodes or [])
        self.tasks = tuple(tasks or [])


class _FakeGraph:
    def __init__(self, snapshot: _FakeSnapshot, invoke_result: dict | None = None):
        self._snapshot = snapshot
        self._invoke_result = invoke_result if invoke_result is not None else {}
        self.invoke_calls: list[tuple[object, object]] = []
        self.state_calls: list[object] = []

    def get_state(self, config):
        self.state_calls.append(config)
        return self._snapshot

    def invoke(self, payload, config):
        self.invoke_calls.append((payload, config))
        return self._invoke_result


@pytest.mark.skipif(not hasattr(mcp_server, "start_new_run"), reason="FastMCP unavailable in this environment")
def test_start_new_run_invokes_graph_with_initial_payload(monkeypatch):
    snapshot = _FakeSnapshot(values={"term_cluster_memory": {"cooccurrence": {"a||b": 1}}})
    invoke_result = {"review_report": {"passed": True}, "task_breakdown": [], "prompt_pack": []}
    fake_graph = _FakeGraph(snapshot=snapshot, invoke_result=invoke_result)

    monkeypatch.setattr(mcp_server, "get_compiled_graph", lambda: fake_graph)
    monkeypatch.setattr(mcp_server, "_generate_project_id", lambda _prefix="run": "run-fixed-001")

    out = mcp_server.start_new_run(raw_requirement="Build a test flow", project_prefix="run")
    assert out["project_id"] == "run-fixed-001"
    assert out["status"] in {"completed", "interrupted"}
    assert len(fake_graph.invoke_calls) == 1
    payload, config = fake_graph.invoke_calls[0]
    assert isinstance(payload, dict)
    assert payload["project_id"] == "run-fixed-001"
    assert payload["thread_id"] == "run-fixed-001"
    assert payload["raw_requirement"] == "Build a test flow"
    assert payload["term_cluster_memory"] == {"cooccurrence": {"a||b": 1}}
    assert config == {"configurable": {"thread_id": "run-fixed-001"}}


@pytest.mark.skipif(not hasattr(mcp_server, "continue_run"), reason="FastMCP unavailable in this environment")
def test_continue_run_returns_interrupted_when_pending_interrupts(monkeypatch):
    snapshot = _FakeSnapshot(
        values={"project_id": "demo-continue"},
        next_nodes=["reviewer"],
        tasks=[_FakeTask(interrupts=[{"missing_info": ["budget"]}])],
    )
    fake_graph = _FakeGraph(snapshot=snapshot, invoke_result={"unexpected": "should_not_happen"})
    monkeypatch.setattr(mcp_server, "get_compiled_graph", lambda: fake_graph)

    out = mcp_server.continue_run(project_id="demo-continue")
    assert out["status"] == "interrupted"
    assert out["project_id"] == "demo-continue"
    assert out["next"] == ["reviewer"]
    assert isinstance(out["interrupts"], list)
    assert len(fake_graph.invoke_calls) == 0


@pytest.mark.skipif(not hasattr(mcp_server, "resume_run_with_feedback"), reason="FastMCP unavailable in this environment")
def test_resume_run_with_feedback_sends_command_and_returns_result(monkeypatch):
    class _FakeCommand:
        def __init__(self, resume):
            self.resume = resume

    snapshot = _FakeSnapshot(values={})
    invoke_result = {
        "project_id": "demo-resume",
        "task_breakdown": [],
        "prompt_pack": [],
        "review_report": {"passed": True},
    }
    fake_graph = _FakeGraph(snapshot=snapshot, invoke_result=invoke_result)

    monkeypatch.setattr(mcp_server, "get_compiled_graph", lambda: fake_graph)
    monkeypatch.setattr(mcp_server, "Command", _FakeCommand)

    feedback = {"deadline": "Q4", "budget": "fixed"}
    out = mcp_server.resume_run_with_feedback(project_id="demo-resume", human_feedback=feedback)
    assert out["project_id"] == "demo-resume"
    assert out["status"] in {"completed", "interrupted"}
    assert len(fake_graph.invoke_calls) == 1
    payload, config = fake_graph.invoke_calls[0]
    assert isinstance(payload, _FakeCommand)
    assert payload.resume == feedback
    assert config == {"configurable": {"thread_id": "demo-resume"}}
