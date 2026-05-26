from types import SimpleNamespace

import app.services.human_interrupt_hook as hook


def test_notify_human_interrupt_required_enqueues_non_blocking(monkeypatch):
    monkeypatch.setattr(
        hook,
        "settings",
        SimpleNamespace(
            human_interrupt_hook_enabled=True,
            human_interrupt_hook_url="http://example.local/hook",
            human_interrupt_hook_token="",
            human_interrupt_hook_timeout_seconds=1.0,
            human_interrupt_hook_idempotency_ttl_seconds=60,
            human_interrupt_hook_idempotency_prefix="hook:test",
            redis_url="redis://127.0.0.1:6379/0",
        ),
    )
    monkeypatch.setattr(hook, "_mark_once_distributed", lambda _key: True)
    monkeypatch.setattr(hook, "_ensure_worker", lambda: None)

    captured = []

    class _Q:
        def put_nowait(self, item):
            captured.append(item)

    monkeypatch.setattr(hook, "_QUEUE", _Q())

    ok = hook.notify_human_interrupt_required(
        project_id="p1",
        checkpoint_id="cp-1",
        source="state_pending_interrupt",
        pending_interrupts=[{"type": "missing_requirement_info"}],
        next_nodes=["human_gate"],
    )
    assert ok is True
    assert len(captured) == 1
    payload = captured[0]
    assert payload["event"] == "human_input_required"
    assert payload["project_id"] == "p1"
    assert payload["checkpoint_id"] == "cp-1"


def test_notify_human_interrupt_required_is_idempotent(monkeypatch):
    monkeypatch.setattr(
        hook,
        "settings",
        SimpleNamespace(
            human_interrupt_hook_enabled=True,
            human_interrupt_hook_url="http://example.local/hook",
            human_interrupt_hook_token="",
            human_interrupt_hook_timeout_seconds=1.0,
            human_interrupt_hook_idempotency_ttl_seconds=60,
            human_interrupt_hook_idempotency_prefix="hook:test",
            redis_url="redis://127.0.0.1:6379/0",
        ),
    )
    calls = {"n": 0}

    def _mark_once(_key):
        calls["n"] += 1
        return calls["n"] == 1

    monkeypatch.setattr(hook, "_mark_once_distributed", _mark_once)
    monkeypatch.setattr(hook, "_ensure_worker", lambda: None)

    captured = []

    class _Q:
        def put_nowait(self, item):
            captured.append(item)

    monkeypatch.setattr(hook, "_QUEUE", _Q())

    first = hook.notify_human_interrupt_required(
        project_id="p1",
        checkpoint_id="cp-1",
        source="state_pending_interrupt",
        pending_interrupts=[{"type": "missing_requirement_info"}],
        next_nodes=["human_gate"],
    )
    second = hook.notify_human_interrupt_required(
        project_id="p1",
        checkpoint_id="cp-1",
        source="state_pending_interrupt",
        pending_interrupts=[{"type": "missing_requirement_info"}],
        next_nodes=["human_gate"],
    )
    assert first is True
    assert second is False
    assert len(captured) == 1
