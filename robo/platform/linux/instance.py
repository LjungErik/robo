"""Make sure only one robot runs at a time (a lock file in the runtime dir)."""
import fcntl
import os

_lock_file = None   # kept open for the lifetime of the process


def acquire_lock():
    global _lock_file
    path = os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/tmp'), 'robot-companion.lock')
    f = open(path, 'w')
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return False
    _lock_file = f
    return True
