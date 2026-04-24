import threading

from app.graph.builder import build_graph
from app.storage.checkpoints import is_checkpointer_healthy

_COMPILED_GRAPH = None
_COMPILED_GRAPH_LOCK = threading.RLock()

def get_compiled_graph():
    global _COMPILED_GRAPH

    with _COMPILED_GRAPH_LOCK:
        if _COMPILED_GRAPH is None:
            _COMPILED_GRAPH = build_graph()
            return _COMPILED_GRAPH

        checkpointer = getattr(_COMPILED_GRAPH, "checkpointer", None)
        if not is_checkpointer_healthy(checkpointer):
            _COMPILED_GRAPH = build_graph()
        return _COMPILED_GRAPH
