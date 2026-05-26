import time

from fastapi.testclient import TestClient

from app.dependencies import get_compiled_graph
from app.graph.nodes.reviewer import _apply_review_outcome
from app.main import app
from app.services.observability import reset_metrics, snapshot_metrics


def _bypass_rate_limit(monkeypatch):
    async def _allow_always(_self, _request, _rule):
        return True, 999

    monkeypatch.setattr(
        "app.api.middleware_rate_limit.RedisRateLimitMiddleware._allow",
        _allow_always,
    )


def test_metrics_endpoint_returns_snapshot(monkeypatch):
    reset_metrics()
    _bypass_rate_limit(monkeypatch)
    client = TestClient(app)
    response = client.get("/runs/_metrics")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert isinstance(payload["metrics"], dict)


def test_prometheus_metrics_endpoint_returns_text():
    reset_metrics()
    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    assert "\n" in response.text


def test_alerts_endpoint_returns_structure():
    reset_metrics()
    client = TestClient(app)
    response = client.get("/alerts")
    assert response.status_code == 200
    payload = response.json()
    assert "active" in payload
    assert "active_count" in payload
    assert "counters" in payload


def test_run_success_increments_workflow_metric(monkeypatch):
    class FakeGraph:
        def get_state(self, _config):
            class Snapshot:
                values = {}

            return Snapshot()

        def invoke(self, _payload, _config):
            return {
                "requirement_doc": {"project_name": "demo", "summary": "x"},
                "feasibility_report": {},
                "architecture_plan": {},
                "task_breakdown": [],
                "prompt_pack": [],
                "review_report": {},
            }

    reset_metrics()
    _bypass_rate_limit(monkeypatch)
    monkeypatch.setattr("app.api.routes_runs._RUNNING_PROJECTS", set())
    app.dependency_overrides[get_compiled_graph] = lambda: FakeGraph()
    try:
        client = TestClient(app)
        response = client.post(
            "/runs",
            json={"project_id": "p-metrics-run", "raw_requirement": "demo"},
        )
        assert response.status_code == 200
        metrics = snapshot_metrics()
        key = "workflow_run_total|status=success"
        assert metrics.get(key, 0.0) >= 1.0
    finally:
        app.dependency_overrides.pop(get_compiled_graph, None)


def test_continue_no_progress_increments_metric(monkeypatch):
    class FakeGraph:
        def invoke(self, _payload, _config):
            return None

        def get_state(self, _config):
            class Snapshot:
                config = {
                    "configurable": {
                        "thread_id": "p-no-progress",
                        "checkpoint_id": "cp-1",
                    }
                }
                next = ("planner",)
                tasks = ()
                values = {}
                metadata = {}
                created_at = None

            return Snapshot()

    reset_metrics()
    _bypass_rate_limit(monkeypatch)
    monkeypatch.setattr("app.api.routes_runs._CONTINUE_JOBS", {})
    monkeypatch.setattr("app.api.routes_runs._CONTINUE_JOB_STATUS", {})
    monkeypatch.setattr("app.api.routes_runs._RUNNING_PROJECTS", set())
    app.dependency_overrides[get_compiled_graph] = lambda: FakeGraph()
    try:
        client = TestClient(app)
        first = client.post("/runs/p-no-progress/continue")
        assert first.status_code == 200
        assert first.json()["status"] == "in_progress"

        latest = None
        for _ in range(30):
            latest = client.post("/runs/p-no-progress/continue")
            assert latest.status_code == 200
            if latest.json()["status"] == "failed":
                break
            time.sleep(0.02)

        assert latest is not None
        assert latest.json()["status"] == "failed"
        metrics = snapshot_metrics()
        assert metrics.get("workflow_continue_no_progress_total", 0.0) >= 1.0
    finally:
        app.dependency_overrides.pop(get_compiled_graph, None)


def test_reviewer_reflow_increments_metric():
    reset_metrics()
    state = {
        "project_id": "p-review-metrics",
        "review_rounds": 0,
        "max_review_rounds": 3,
        "errors": [],
    }
    review_report = {
        "passed": False,
        "issues": ["关键路径缺失依赖处理"],
        "suggestions": ["补齐任务"],
    }
    out = _apply_review_outcome(state, review_report, passed=False)
    assert out["next_step"] in {"planner", "prompt_builder", "finish"}
    metrics = snapshot_metrics()
    assert any(
        key.startswith("review_reflow_total|")
        and ("target=planner" in key or "target=prompt_builder" in key or "target=finish" in key)
        for key in metrics
    )
