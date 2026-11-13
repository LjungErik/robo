"""Task worker: runs INSIDE the sandbox, one process per task.

Started by a SandboxBackend as `python3 -I main.py`, in the task's work
folder. It only imports the standard library and its neighbours in this
folder (none of Robo itself), reads one 'start' message, runs the job and
reports back:

    in   {"type": "start", "job": "placeholder", "args": {...},
          "inputs": {name: path}, "files": {name: path}}
    out  {"type": "progress", "value": 0.4}
         {"type": "log", "text": "..."}
         {"type": "request", "id": 1, "op": "fetch", "url": "..."}  -> reply
         {"type": "done", "result": ...}   or   {"type": "error", "message": "..."}

stdout is reserved for these messages; anything a job prints goes to the log.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api import Channel, TaskAPI  # noqa: E402
from jobs import JOBS  # noqa: E402


def main():
    proto_out = os.fdopen(os.dup(1), 'w', buffering=1)
    os.dup2(2, 1)                        # stray print()s go to the log, not the protocol
    chan = Channel(sys.stdin, proto_out)
    start = chan.read()
    if not start or start.get('type') != 'start':
        chan.send({'type': 'error', 'message': 'expected a start message'})
        return 2
    job = JOBS.get(start.get('job'))
    if job is None:
        chan.send({'type': 'error', 'message': f"unknown job: {start.get('job')}"})
        return 2
    api = TaskAPI(chan, start.get('inputs') or {}, start.get('files') or {})
    try:
        result = job(api, **(start.get('args') or {}))
    except Exception as e:
        traceback.print_exc()
        chan.send({'type': 'error', 'message': f'{type(e).__name__}: {e}'})
        return 1
    try:
        json.dumps(result)
    except (TypeError, ValueError):
        result = str(result)
    chan.send({'type': 'done', 'result': result})
    return 0


if __name__ == '__main__':
    sys.exit(main())
