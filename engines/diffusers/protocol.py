# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Line protocol between the app (src/main/engines.ts) and an engine process.

In:  one JSON object per line, {"op": "generate" | "preview" | "stop" | "unload" | "ping", "job": {...}}
Out: one event per line, "@vk " followed by JSON, {"event": "state" | "progress" | "status" | "result" | "error" |
     "preview" | "pong", ...}. Other output on stdout (libraries) is not an event and only logged by the app.

A reader thread owns stdin, so a stop request is seen while a job runs and no other request is lost.
"""
import contextlib
import ctypes
import json
import os
import queue
import sys
import threading

PREFIX = "@vk "
OPS = ("generate", "preview", "stop", "unload", "ping")


def parse_line(line):
    """(op, job) of a request line, None for anything else."""
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        req = json.loads(line)
    except ValueError:
        return None
    if not isinstance(req, dict) or req.get("op") not in OPS:
        return None
    job = req.get("job")
    return req["op"], job if isinstance(job, dict) else {}


# requests that start a job; a stop after one of them is about that job
JOB_OPS = ("generate", "preview")


def describe(e):
    """An error as the app shows it: a missing key of the job or of a model.json is named as such."""
    if isinstance(e, KeyError):
        return "The job or the model's model.json lacks %s" % (e.args[0] if e.args else "a value")
    return str(e)


class CommandReader:
    def __init__(self, stream=None):
        self.stream = stream or sys.stdin
        self.commands = queue.Queue()
        self.stop_event = threading.Event()
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.interrupt = None  # (thread id, exception class) while that thread loads a model (interruptible())
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def _run(self):
        for line in self.stream:
            parsed = parse_line(line)
            if parsed is None:
                continue
            if parsed[0] == "stop":
                self.stop_event.set()
                with self.lock:
                    if self.interrupt is not None:
                        _raise_in(*self.interrupt)
                        self.interrupt = None
            else:
                if parsed[0] in JOB_OPS:
                    # a stop is about the job read before it: cleared here, in the order of stdin, not when the
                    # job starts (a stop sent while the engine was still starting or loading would be lost then)
                    self.stop_event.clear()
                self.commands.put(parsed)
        self.closed.set()
        self.commands.put(None)

    def next_command(self):
        """Blocks until a request arrives: (op, job); None once stdin is closed."""
        return self.commands.get()

    def stop_requested(self):
        return self.stop_event.is_set()

    @contextlib.contextmanager
    def interruptible(self, exc):
        """While the calling thread loads a model: a stop raises exc there at once (between two tensors) instead of
        after the whole load. Only around code whose files are written whole or renamed into place: a cache file
        written half would be read next time."""
        if self.stop_event.is_set():
            raise exc()
        tid = threading.get_ident()
        with self.lock:
            self.interrupt = (tid, exc)
        try:
            yield
        finally:
            with self.lock:
                self.interrupt = None
                _raise_in(tid, None)  # a stop raised but not yet delivered is taken back


def _raise_in(tid, exc):
    """Raises exc in the thread tid at its next Python instruction (None takes a pending one back)."""
    ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(tid), ctypes.py_object(exc) if exc else None)


def event(name, **fields):
    sys.stdout.write(PREFIX + json.dumps(dict(event=name, **fields)) + "\n")
    sys.stdout.flush()


def note(message):
    """How the job was made, shown with its result (e.g. step caching)."""
    event("note", message=message)


def precision(parts):
    """The bit size each part of the model runs in for this job (benchmarks): [("transformer", "8 bit"), ...]."""
    event("precision", message=", ".join("%s %s" % (name.replace("_", " "), label) for name, label in parts))


def waited(what, seconds, gb):
    """Time the steps of this picture spent waiting for parts of the model to be read again (benchmarks); what:
    "ssd_stream" (blocks of a model streamed from the SSD)."""
    event("waited", what=what, seconds=round(seconds, 1), gb=round(gb, 2))


# what the memory plan expected for the running job (GB), reported with its footprint (benchmarks)
PLANNED = {"gb": None}


def planned(gb):
    PLANNED["gb"] = round(gb, 2) if gb is not None else None
    if gb is not None:
        event("planned", gb=PLANNED["gb"])  # the monitor window shows the job's memory against it while it runs


class Footprint:
    """The memory footprint (with what the GPU holds) and the disk reads of the engine's processes over one job, as
    macOS counts them (proc_pid_rusage): the peak of each process since start() summed, and what they read."""

    def __init__(self, pids=lambda: [os.getpid()]):
        self.pids = pids
        self.read = {}

    @staticmethod
    def _usage(pid):
        import ctypes
        lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        names = ("user_time system_time pkg_idle_wkups interrupt_wkups pageins wired_size resident_size phys_footprint "
                 "proc_start_abstime proc_exit_abstime child_user_time child_system_time child_pkg_idle_wkups "
                 "child_interrupt_wkups child_pageins child_elapsed_abstime diskio_bytesread diskio_byteswritten "
                 "cpu_time_qos_default cpu_time_qos_maintenance cpu_time_qos_background cpu_time_qos_utility "
                 "cpu_time_qos_legacy cpu_time_qos_user_initiated cpu_time_qos_user_interactive billed_system_time "
                 "serviced_system_time logical_writes lifetime_max_phys_footprint instructions cycles billed_energy "
                 "serviced_energy interval_max_phys_footprint runnable_time").split()

        class Usage(ctypes.Structure):  # rusage_info_v4
            _fields_ = [("uuid", ctypes.c_uint8 * 16)] + [(n, ctypes.c_uint64) for n in names]
        u = Usage()
        if lib.proc_pid_rusage(pid, 4, ctypes.byref(u)) != 0:
            return None
        return lib, u

    def start(self):
        PLANNED["gb"] = None
        self.read = {}
        for pid in self.pids():
            got = self._usage(pid)
            if got:
                got[0].proc_reset_footprint_interval(pid)
                self.read[pid] = got[1].diskio_bytesread

    def report(self):
        peak = read = 0
        for pid in self.pids():
            got = self._usage(pid)
            if got:
                peak += got[1].interval_max_phys_footprint
                read += got[1].diskio_bytesread - self.read.get(pid, 0)  # a process started during the job: all it read
        if peak:
            event("footprint", peak_gb=round(peak / 1024 ** 3, 2), read_gb=round(read / 1024 ** 3, 2), plan_gb=PLANNED["gb"])


def footprint_gb(pid=None):
    """What this process (or pid) holds now (with the GPU's share), as macOS counts it."""
    got = Footprint._usage(pid or os.getpid())
    return got[1].phys_footprint / 1024 ** 3 if got else 0.0


def state(value):
    """"loaded" (process started), "idle" (ready for a job), "busy" (working on one)."""
    event("state", state=value)


def progress(value):
    """Percent of the current job, -1 while it can not be told."""
    event("progress", value=value)


def status(message):
    event("status", message=message)


def result(path):
    event("result", path=str(path))


def error(message):
    event("error", message=str(message))


def preview(info):
    """{"model", "preview"} or {"model", "error"}: a model painted its own preview picture."""
    event("preview", **info)


def log(*args):
    print(*args, file=sys.stderr, flush=True)
