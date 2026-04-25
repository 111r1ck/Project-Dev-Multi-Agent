from fastapi.testclient import TestClient

from app.main import app


def test_index_page_served():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "LangGraph Multi-Agent Console" in response.text


def test_human_feedback_form_keeps_split_fields_and_raw_json_modes():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "missingFieldsWrap" in html
    assert "feedbackText" in html
    assert "renderMissingFieldRows" in html
    assert "syncFeedbackJsonFromFields" in html
    assert "JSON.parse(feedbackText.value)" in html
