from app.storage.checkpoints import is_checkpointer_healthy


class DummyConn:
    def __init__(self, closed=False, broken=False):
        self.closed = closed
        self.broken = broken


class DummyCheckpointer:
    def __init__(self, conn):
        self.conn = conn


def test_is_checkpointer_healthy_when_open():
    cp = DummyCheckpointer(DummyConn(closed=False, broken=False))
    assert is_checkpointer_healthy(cp) is True


def test_is_checkpointer_healthy_when_closed():
    cp = DummyCheckpointer(DummyConn(closed=True, broken=False))
    assert is_checkpointer_healthy(cp) is False


def test_is_checkpointer_healthy_when_broken():
    cp = DummyCheckpointer(DummyConn(closed=False, broken=True))
    assert is_checkpointer_healthy(cp) is False
