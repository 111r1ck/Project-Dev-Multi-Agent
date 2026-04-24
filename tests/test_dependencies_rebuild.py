import app.dependencies as deps


class FakeGraph:
    def __init__(self, checkpointer):
        self.checkpointer = checkpointer


class FakeConn:
    def __init__(self, closed=False):
        self.closed = closed
        self.broken = False


class FakeCheckpointer:
    def __init__(self, closed=False):
        self.conn = FakeConn(closed=closed)


def test_get_compiled_graph_rebuilds_on_unhealthy(monkeypatch):
    created = []

    def fake_build_graph():
        if not created:
            g = FakeGraph(FakeCheckpointer(closed=False))
        else:
            g = FakeGraph(FakeCheckpointer(closed=False))
        created.append(g)
        return g

    monkeypatch.setattr(deps, "build_graph", fake_build_graph)
    deps._COMPILED_GRAPH = None

    first = deps.get_compiled_graph()
    assert first is created[0]

    # Simulate stale/closed connection on cached graph
    first.checkpointer.conn.closed = True
    second = deps.get_compiled_graph()
    assert second is not first
    assert len(created) == 2
