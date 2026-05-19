from app.services.export_service import export_run_artifact


def _sample_values():
    return {
        "project_id": "demo",
        "task_breakdown": [{"title": "t1", "priority": "P0", "owner_role": "后端", "depends_on": []}],
        "prompt_pack": [{"task_title": "t1", "coding_prompt": "x", "test_prompt": "y"}],
        "review_report": {"passed": True, "issues": [], "suggestions": [], "diagnostics": []},
    }


def test_export_run_artifact_json(tmp_path):
    result = export_run_artifact(
        project_id="demo",
        values=_sample_values(),
        export_format="json",
        sections=["summary", "tasks", "review"],
        base_dir=str(tmp_path),
    )
    assert result["format"] == "json"
    assert result["size_bytes"] > 0
    assert result["file_path"].endswith(".json")


def test_export_run_artifact_csv(tmp_path):
    result = export_run_artifact(
        project_id="demo",
        values=_sample_values(),
        export_format="csv",
        sections=["tasks", "diagnostics"],
        base_dir=str(tmp_path),
    )
    assert result["format"] == "csv"
    assert result["size_bytes"] > 0
    assert result["file_path"].endswith(".csv")
