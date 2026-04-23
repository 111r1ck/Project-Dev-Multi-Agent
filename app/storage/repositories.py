from typing import Any


class RunRepository:
    def save_run_result(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"project_id": project_id, "payload": payload}
