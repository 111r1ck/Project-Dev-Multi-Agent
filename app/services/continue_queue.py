from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ContinueJobHandle:
    project_id: str
    _done: bool = False
    _lock: threading.RLock = threading.RLock()

    def is_alive(self) -> bool:
        with self._lock:
            return not self._done

    def mark_done(self) -> None:
        with self._lock:
            self._done = True


_TASK_QUEUE: queue.Queue[tuple[ContinueJobHandle, Callable[..., Any], tuple[Any, ...], dict[str, Any]]] = queue.Queue()
_WORKER_LOCK = threading.RLock()
_WORKER_THREAD: threading.Thread | None = None


def _worker_loop() -> None:
    while True:
        handle, fn, args, kwargs = _TASK_QUEUE.get()
        try:
            fn(*args, **kwargs)
        finally:
            handle.mark_done()
            _TASK_QUEUE.task_done()


def _ensure_worker() -> None:
    global _WORKER_THREAD
    with _WORKER_LOCK:
        if _WORKER_THREAD is not None and _WORKER_THREAD.is_alive():
            return
        _WORKER_THREAD = threading.Thread(
            target=_worker_loop,
            name="continue-queue-worker",
            daemon=True,
        )
        _WORKER_THREAD.start()


def enqueue_continue_job(
    project_id: str,
    fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> ContinueJobHandle:
    _ensure_worker()
    handle = ContinueJobHandle(project_id=project_id)
    _TASK_QUEUE.put((handle, fn, args, kwargs))
    return handle


def get_queue_size() -> int:
    return _TASK_QUEUE.qsize()

