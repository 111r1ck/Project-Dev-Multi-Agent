from pathlib import Path

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
