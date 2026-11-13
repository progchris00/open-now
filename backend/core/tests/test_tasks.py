from core.tasks import ping


def test_ping_returns_pong() -> None:
    assert ping.run() == "pong"
