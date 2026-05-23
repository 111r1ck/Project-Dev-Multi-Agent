from pathlib import Path
import time

from app.api.routes_runs import _format_run_response, _serialize_snapshot
from app.dependencies import get_compiled_graph
from app.main import app
from fastapi.testclient import TestClient


class FakeInterrupt:
    def __init__(self, value):
        self.value = value


class FakeTask:
    def __init__(self):
        self.id = "t1"
        self.name = "human_gate"
        self.error = None
        self.interrupts = [FakeInterrupt({"type": "missing_requirement_info"})]


class FakeSnapshot:
    def __init__(self):
        self.config = {
            "configurable": {
                "thread_id": "p3",
                "checkpoint_id": "cp-1",
                "checkpoint_ns": "",
            }
        }
        self.metadata = {"step": 2}
        self.values = {"next_step": "human_gate"}
        self.next = ("human_gate",)
        self.tasks = (FakeTask(),)
        self.created_at = None


class FakeSnapshotWithCreatedAtString(FakeSnapshot):
    def __init__(self):
        super().__init__()
        self.created_at = "2026-04-23T12:00:00+08:00"


def test_format_run_response_completed():
    result = {
        "requirement_doc": {"project_name": "demo", "summary": "x"},
        "feasibility_report": {},
        "architecture_plan": {},
        "task_breakdown": [],
        "prompt_pack": [],
        "review_report": {},
    }
    response = _format_run_response("p1", result)
    assert response["status"] == "completed"
    assert response["project_id"] == "p1"
    assert "result" in response


def test_format_run_response_interrupted():
    result = {"__interrupt__": [FakeInterrupt({"message": "need info"})]}
    response = _format_run_response("p2", result)
    assert response["status"] == "interrupted"
    assert response["interrupts"][0]["message"] == "need info"


def test_serialize_snapshot():
    serialized = _serialize_snapshot(FakeSnapshot())
    assert serialized["thread_id"] == "p3"
    assert serialized["checkpoint_id"] == "cp-1"
    assert serialized["next"] == ["human_gate"]
    assert serialized["tasks"][0]["name"] == "human_gate"


def test_serialize_snapshot_with_created_at_string():
    serialized = _serialize_snapshot(FakeSnapshotWithCreatedAtString())
    assert serialized["created_at"] == "2026-04-23T12:00:00+08:00"


def test_persist_env_accepts_inline_agent_setting_updates(monkeypatch):
    env_file = Path(".tmp_test_agents.env")
    env_file.write_text("PLANNER_LLM_MODEL=old-model\n", encoding="utf-8")

    def fake_persist(env_path=None):
        from app.services.env_persistence import persist_runtime_settings_to_env

        return persist_runtime_settings_to_env(env_path=env_file)

    monkeypatch.setattr("app.api.routes_agents.persist_runtime_settings_to_env", fake_persist)

    try:
        client = TestClient(app)
        response = client.post(
            "/agents/settings/persist-env",
            json={"planner_llm_model": "glm-5"},
        )

        assert response.status_code == 200
        assert "PLANNER_LLM_MODEL=glm-5" in env_file.read_text(encoding="utf-8")
    finally:
        env_file.unlink(missing_ok=True)


def test_continue_reports_failed_status_after_background_error(monkeypatch):
    class FakeGraph:
        def invoke(self, payload, config):
            raise RuntimeError("boom")

        def get_state(self, _config):
            class Snapshot:
                next = ("planner",)
                tasks = ()
                values = {}
            return Snapshot()

    monkeypatch.setattr("app.api.routes_runs._CONTINUE_JOBS", {})
    monkeypatch.setattr("app.api.routes_runs._CONTINUE_JOB_STATUS", {})
    async def _allow_always(_self, _request, _rule):
        return True, 999

    monkeypatch.setattr(
        "app.api.middleware_rate_limit.RedisRateLimitMiddleware._allow",
        _allow_always,
    )
    app.dependency_overrides[get_compiled_graph] = lambda: FakeGraph()

    try:
        client = TestClient(app)
        first = client.post("/runs/p-fail/continue")
        assert first.status_code == 200
        assert first.json()["status"] == "in_progress"

        second = None
        for _ in range(20):
            second = client.post("/runs/p-fail/continue")
            assert second.status_code == 200
            if second.json()["status"] == "failed":
                break
            time.sleep(0.02)

        assert second is not None
        assert second.json()["status"] == "failed"
        assert "boom" in second.json().get("error", "")
    finally:
        app.dependency_overrides.pop(get_compiled_graph, None)


def test_state_includes_continue_status(monkeypatch):
    class FakeGraph:
        def get_state(self, _config):
            class Snapshot:
                config = {"configurable": {"thread_id": "p-state"}}
                metadata = {}
                values = {"x": 1}
                next = ("planner",)
                tasks = ()
                created_at = None

            return Snapshot()

    monkeypatch.setattr(
        "app.api.routes_runs._CONTINUE_JOB_STATUS",
        {"p-state": {"status": "failed", "error": "boom"}},
    )
    app.dependency_overrides[get_compiled_graph] = lambda: FakeGraph()

    try:
        client = TestClient(app)
        response = client.get("/runs/p-state/state")
        assert response.status_code == 200
        payload = response.json()
        assert payload["continue_status"]["status"] == "failed"
        assert payload["continue_status"]["error"] == "boom"
    finally:
        app.dependency_overrides.pop(get_compiled_graph, None)


def test_run_rejects_when_project_is_already_running(monkeypatch):
    class FakeGraph:
        def get_state(self, _config):
            class Snapshot:
                values = {}

            return Snapshot()

        def invoke(self, payload, config):
            return payload

    monkeypatch.setattr("app.api.routes_runs._RUNNING_PROJECTS", {"p-lock"})
    async def _allow_always(_self, _request, _rule):
        return True, 999

    monkeypatch.setattr(
        "app.api.middleware_rate_limit.RedisRateLimitMiddleware._allow",
        _allow_always,
    )
    app.dependency_overrides[get_compiled_graph] = lambda: FakeGraph()

    try:
        client = TestClient(app)
        response = client.post(
            "/runs",
            json={"project_id": "p-lock", "raw_requirement": "demo requirement"},
        )
        assert response.status_code == 409
        assert "已有执行中的 run/resume/continue 请求" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_compiled_graph, None)


def test_resume_rejects_when_project_is_already_running(monkeypatch):
    class FakeGraph:
        def invoke(self, payload, config):
            return {"ok": True}

    monkeypatch.setattr("app.api.routes_runs._RUNNING_PROJECTS", {"p-lock"})
    async def _allow_always(_self, _request, _rule):
        return True, 999

    monkeypatch.setattr(
        "app.api.middleware_rate_limit.RedisRateLimitMiddleware._allow",
        _allow_always,
    )
    app.dependency_overrides[get_compiled_graph] = lambda: FakeGraph()

    try:
        client = TestClient(app)
        response = client.post(
            "/runs/p-lock/resume",
            json={"human_feedback": {"note": "x"}},
        )
        assert response.status_code == 409
        assert "已有执行中的 run/resume/continue 请求" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_compiled_graph, None)


def test_continue_returns_in_progress_when_project_is_running(monkeypatch):
    class FakeGraph:
        def get_state(self, _config):
            class Snapshot:
                next = ("planner",)
                tasks = ()
                values = {}
                config = {"configurable": {"thread_id": "p-lock"}}

            return Snapshot()

    monkeypatch.setattr("app.api.routes_runs._CONTINUE_JOBS", {})
    monkeypatch.setattr("app.api.routes_runs._CONTINUE_JOB_STATUS", {})
    monkeypatch.setattr("app.api.routes_runs._RUNNING_PROJECTS", {"p-lock"})
    async def _allow_always(_self, _request, _rule):
        return True, 999

    monkeypatch.setattr(
        "app.api.middleware_rate_limit.RedisRateLimitMiddleware._allow",
        _allow_always,
    )
    app.dependency_overrides[get_compiled_graph] = lambda: FakeGraph()

    try:
        client = TestClient(app)
        response = client.post("/runs/p-lock/continue")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "in_progress"
        assert "已有执行中的 run/resume/continue 请求" in payload["message"]
    finally:
        app.dependency_overrides.pop(get_compiled_graph, None)


def test_run_releases_project_lock_after_failure(monkeypatch):
    class FakeGraph:
        def get_state(self, _config):
            class Snapshot:
                values = {}

            return Snapshot()

        def invoke(self, _payload, _config):
            raise RuntimeError("invoke failed")

    running_projects: set[str] = set()
    monkeypatch.setattr("app.api.routes_runs._RUNNING_PROJECTS", running_projects)
    app.dependency_overrides[get_compiled_graph] = lambda: FakeGraph()

    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/runs",
            json={"project_id": "p-failure", "raw_requirement": "demo requirement"},
        )
        assert response.status_code == 500
        assert "p-failure" not in running_projects
    finally:
        app.dependency_overrides.pop(get_compiled_graph, None)
