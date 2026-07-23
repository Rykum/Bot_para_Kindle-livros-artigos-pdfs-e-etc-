import threading
import time

from app.bot_service import BotService


class FakeBot:
    def __init__(self):
        self.cleaned_up = False

    def cleanup(self):
        self.cleaned_up = True


def make_service(events):
    return BotService(bot_factory=FakeBot, event_sink=lambda name, payload: events.append((name, payload)))


def test_run_sync_returns_result_and_uses_bot():
    events = []
    service = make_service(events)
    service.start()
    try:
        result = service.run_sync("read", lambda bot, emit: isinstance(bot, FakeBot))
        assert result is True
    finally:
        service.stop()


def test_jobs_never_overlap():
    events = []
    service = make_service(events)
    service.start()
    active = {"count": 0, "max": 0}
    lock = threading.Lock()

    def slow(bot, emit):
        with lock:
            active["count"] += 1
            active["max"] = max(active["max"], active["count"])
        time.sleep(0.02)
        with lock:
            active["count"] -= 1
        return "ok"

    try:
        ids = [service.submit(f"job{i}", slow) for i in range(5)]
        deadline = time.time() + 5
        done = set()
        while len(done) < 5 and time.time() < deadline:
            for name, payload in list(events):
                if name == "job_done":
                    done.add(payload["job_id"])
            time.sleep(0.01)
        assert done == set(ids)
        assert active["max"] == 1  # nunca dois jobs simultâneos
    finally:
        service.stop()


def test_error_emits_job_error():
    events = []
    service = make_service(events)
    service.start()

    def boom(bot, emit):
        raise ValueError("falhou")

    try:
        service.submit("bad", boom)
        deadline = time.time() + 5
        while time.time() < deadline:
            if any(n == "job_error" for n, _ in events):
                break
            time.sleep(0.01)
        errors = [p for n, p in events if n == "job_error"]
        assert errors and "falhou" in errors[0]["error"]
    finally:
        service.stop()


def test_cancel_marks_job():
    events = []
    service = make_service(events)
    service.start()
    try:
        job_id = service.submit("long", lambda bot, emit: time.sleep(0.05))
        service.cancel(job_id)
        assert service.is_cancelled(job_id) is True
    finally:
        service.stop()


def test_double_stop_is_safe():
    events = []
    service = make_service(events)
    service.start()
    service.stop()
    # Calling stop() again with no worker running must not raise, and must not
    # leave a stray sentinel behind: a subsequent start() has to process real
    # jobs, not immediately die on a leftover sentinel from the double stop.
    service.stop()

    service.start()
    try:
        result = service.run_sync("after-double-stop", lambda bot, emit: 1, timeout=2)
        assert result == 1
    finally:
        service.stop()


def test_restart_after_stop_processes_jobs():
    events = []
    service = make_service(events)
    # stop() before start() must be a safe no-op — no sentinel should be left
    # sitting in the queue for the next start() to choke on.
    service.stop()

    service.start()
    try:
        result = service.run_sync("read-again", lambda bot, emit: 42, timeout=2)
        assert result == 42
    finally:
        service.stop()


def test_double_stop_while_busy_leaves_no_orphan_sentinel():
    events = []
    service = make_service(events)
    service.start()
    try:
        service.submit("slow", lambda bot, emit: time.sleep(0.3))

        # Give the worker a moment to actually pick up the job so both stop()
        # calls below race while it is busy (not while the queue is empty).
        time.sleep(0.05)

        threads = [threading.Thread(target=service.stop) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
    finally:
        # Make sure no worker is left running before we restart.
        service.stop()

    # If an orphan sentinel was left behind, this start() spawns a worker
    # that immediately consumes it and dies without ever touching the queue
    # again — the run_sync below would then time out.
    service.start()
    try:
        result = service.run_sync("after-busy-double-stop", lambda bot, emit: 7, timeout=2)
        assert result == 7
    finally:
        service.stop()


def test_run_sync_quiet_suppresses_lifecycle_events():
    events = []
    service = make_service(events)
    service.start()
    try:
        result = service.run_sync("quiet-read", lambda bot, emit: 99, quiet=True)
        assert result == 99
        assert not any(n == "job_started" for n, _ in events)
        assert not any(n == "job_done" for n, _ in events)

        events.clear()
        result = service.run_sync("loud-read", lambda bot, emit: 1, quiet=False)
        assert result == 1
        assert any(n == "job_started" for n, _ in events)
        assert any(n == "job_done" for n, _ in events)
    finally:
        service.stop()


def test_run_sync_quiet_still_emits_job_error_on_exception():
    events = []
    service = make_service(events)
    service.start()

    def boom(bot, emit):
        raise ValueError("silenciosa mas falhou")

    try:
        raised = None
        try:
            service.run_sync("quiet-boom", boom, quiet=True)
        except ValueError as exc:
            raised = exc
        assert raised is not None and "silenciosa mas falhou" in str(raised)
        assert not any(n == "job_started" for n, _ in events)
        assert not any(n == "job_done" for n, _ in events)
        assert any(n == "job_error" for n, _ in events)
    finally:
        service.stop()


def test_restart_uses_fresh_bot():
    events = []
    instantiations = {"count": 0}

    class TrackedBot:
        def __init__(self):
            instantiations["count"] += 1
            self.cleaned_up = False

        def cleanup(self):
            self.cleaned_up = True

    service = BotService(bot_factory=TrackedBot, event_sink=lambda name, payload: events.append((name, payload)))

    service.start()
    try:
        service.run_sync("job1", lambda bot, emit: None, timeout=2)
    finally:
        service.stop()

    service.start()
    try:
        bot_state = {}
        service.run_sync("job2", lambda bot, emit: bot_state.update(cleaned_up=bot.cleaned_up), timeout=2)
    finally:
        service.stop()

    assert instantiations["count"] == 2
    assert bot_state["cleaned_up"] is False
