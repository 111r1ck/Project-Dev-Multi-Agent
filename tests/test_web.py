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


def test_persist_env_button_posts_current_agent_form_payload():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    html = response.text

    assert 'const updates = collectAgentSettingsPayload();' in html
    assert 'body: JSON.stringify(updates)' in html
    assert '"/agents/settings/persist-env"' in html
