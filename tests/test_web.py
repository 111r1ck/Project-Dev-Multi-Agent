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


def test_continue_button_triggers_polling_after_in_progress():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    html = response.text

    assert "async function pollAfterContinue(" in html
    assert "if (data && data.status === \"in_progress\")" in html
    assert "await pollAfterContinue(pidRaw);" in html


def test_workflow_buttons_lock_while_execution_is_in_progress():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    html = response.text

    assert "let executionInProgress = false;" in html
    assert "function refreshActionButtons()" in html
    assert "const workflowLocked = loading || executionInProgress;" in html
    assert "const infoRefreshLocked = loading && !executionInProgress;" in html
    assert "runBtn.disabled = workflowLocked;" in html
    assert "continueBtn.disabled = workflowLocked;" in html
    assert "stateBtn.disabled = infoRefreshLocked;" in html
    assert "historyBtn.disabled = infoRefreshLocked;" in html


def test_state_summary_includes_continue_diagnostics():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    html = response.text

    assert "continue_alive" in html
    assert "continue_status" in html
    assert "continue_error" in html
