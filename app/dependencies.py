from functools import lru_cache

from app.graph.builder import build_graph


@lru_cache(maxsize=1)
def get_compiled_graph():
    return build_graph()
