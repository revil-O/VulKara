# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
import io
import json
import threading
import time

import protocol


def test_parse():
    line = json.dumps({"op": "generate", "job": {"a": '{"op": 1}'}}) + "\n"
    assert protocol.parse_line(line) == ("generate", {"a": '{"op": 1}'})
    assert protocol.parse_line('{"op": "unload"}') == ("unload", {})
    assert protocol.parse_line("random log") is None
    assert protocol.parse_line('{"op": "something else"}') is None


def test_stop_does_not_swallow_requests():
    stream = io.StringIO('{"op": "generate", "job": {"n": 1}}\n{"op": "stop"}\n{"op": "generate", "job": {"n": 2}}\n')
    r = protocol.CommandReader(stream).start()
    assert r.next_command() == ("generate", {"n": 1})
    assert r.next_command() == ("generate", {"n": 2})
    assert r.next_command() is None
    # the stop was about job 1: reading job 2 cleared it
    assert not r.stop_requested()


def test_a_stop_sent_before_the_job_starts_is_kept():
    # Cancel while the engine is still starting or loading: the stop is read before the job begins and must hold
    stream = io.StringIO('{"op": "generate", "job": {"n": 1}}\n{"op": "stop"}\n')
    r = protocol.CommandReader(stream).start()
    assert r.next_command() == ("generate", {"n": 1})
    assert r.next_command() is None  # everything read: the stop came in before the job "started"
    assert r.stop_requested()


class Stopped(Exception):
    pass


def test_a_stop_breaks_off_a_load_at_once_and_only_there():
    send = threading.Event()

    def lines():  # stdin: a stop once the test asks for it
        send.wait()
        yield '{"op": "stop"}\n'
    r = protocol.CommandReader(lines()).start()
    t0 = time.time()
    try:
        with r.interruptible(Stopped):
            send.set()
            while time.time() - t0 < 5:  # "loading": the stop lands between two of these instructions
                time.sleep(0.01)
        assert False, "the stop did not break off the load"
    except Stopped:
        pass
    assert r.interrupt is None and r.stop_requested()
    r.stop_event.clear()
    r.closed.wait(2)
    time.sleep(0.05)  # a stop after the load only sets the event
    r2 = protocol.CommandReader(io.StringIO('{"op": "stop"}\n')).start()
    r2.closed.wait(2)
    time.sleep(0.05)
    assert r2.stop_requested()
    try:
        with r2.interruptible(Stopped):  # a stop already there ends the load before it starts
            assert False
    except Stopped:
        pass


def test_events_are_prefixed_json(capsys):
    protocol.progress(42.5)
    protocol.result("/tmp/a.png")
    protocol.state("idle")
    lines = capsys.readouterr().out.splitlines()
    assert all(line.startswith(protocol.PREFIX) for line in lines)
    events = [json.loads(line[len(protocol.PREFIX):]) for line in lines]
    assert events == [{"event": "progress", "value": 42.5}, {"event": "result", "path": "/tmp/a.png"},
                      {"event": "state", "state": "idle"}]
