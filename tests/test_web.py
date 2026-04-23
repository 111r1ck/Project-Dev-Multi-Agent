from fastapi.testclient import TestClient

from app.main import app


def test_index_page_served():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "LangGraph Multi-Agent Console" in response.text
