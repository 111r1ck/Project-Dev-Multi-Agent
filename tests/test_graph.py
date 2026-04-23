from app.graph.builder import build_graph


def test_graph_compile():
    graph = build_graph()
    assert graph is not None
