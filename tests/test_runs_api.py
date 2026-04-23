from app.api.routes_runs import _format_run_response, _serialize_snapshot


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
