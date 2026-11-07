"""review_web: the server stops (as Ctrl+C) once its last browser tab is gone and none came back."""
import json
import threading
import urllib.request

import review_web
from review_store import Store
from review_web import Presence, make_server


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_never_idle_when_no_tab_ever_came():
    c = Clock()
    p = Presence(c)
    c.t += 10_000
    assert not p.idle()


def test_idle_after_the_last_goodbye_and_the_grace():
    c = Clock()
    p = Presence(c)
    p.hello("a"), p.hello("b")
    p.bye("a")
    c.t += 60
    p.hello("b")
    assert not p.idle()  # b still open
    p.bye("b")
    c.t += Presence.GRACE - 1
    assert not p.idle()
    c.t += 1
    assert p.idle()


def test_reload_within_the_grace_keeps_it():
    c = Clock()
    p = Presence(c)
    p.hello("a")
    p.bye("a")
    c.t += 2
    p.hello("b")  # the reloaded page, or Review -> Merge
    c.t += 30
    p.hello("b")
    assert not p.idle()
    p.hello("a")  # a late beat of the tab gone: not counted
    p.bye("b")
    c.t += Presence.GRACE
    assert p.idle()


def test_a_tab_silent_without_goodbye_counts_gone_after_stale():
    c = Clock()
    p = Presence(c)
    p.hello("a")
    c.t += Presence.STALE  # a hidden tab beats once a minute: still there
    assert not p.idle()
    c.t += Presence.GRACE + 1
    assert p.idle()


def test_endpoints_and_the_thread_stops_the_server(data_dir, monkeypatch):
    docs = data_dir.parent / "docs"
    server, token = make_server(Store(data_dir, docs), docs / "review_queue.json", port=0)
    threading.Thread(target=server.serve_forever, args=(0.02,), daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def post(path, body):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"X-Token": token})
        with urllib.request.urlopen(req) as r:
            return r.status

    clock = Clock()
    server.presence.clock = clock
    assert post("/api/alive", {"tab": "t1"}) == 200 and server.presence.ever
    assert post("/api/bye", {"tab": "t1"}) == 200 and not server.presence.tabs
    t = review_web.stop_when_idle(server.presence, server.shutdown, every=0.01)
    t.join(0.2)
    assert t.is_alive()  # within the grace
    clock.t += 3600
    t.join(2)
    assert not t.is_alive()
    server.server_close()
