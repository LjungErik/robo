"""The jobs a task worker can run. Each is `job(api, **args) -> result`.

Jobs run inside the sandbox, so they can only reach what TaskAPI offers
(see api.py). To add one: write the function, add it to JOBS, and add a
task kind for it in robo/tasks/catalog.py (that's where its Permissions
are declared).
"""
import os
import socket
import time

STEP = 0.25


def placeholder(api, seconds=90.0):
    """Pretends to hack for `seconds` of working time, then writes a report."""
    worked = 0.0
    last = time.monotonic()
    reported = -1
    while worked < seconds:
        time.sleep(STEP)
        now = time.monotonic()
        worked += min(now - last, STEP * 2)    # time spent paused doesn't count
        last = now
        pct = int(worked / seconds * 100)
        if pct != reported:
            reported = pct
            api.progress(worked / seconds)
    with open(os.path.join(api.work_dir, 'report.txt'), 'w') as f:
        f.write('Mainframe hacked. (Not really: this was a placeholder task.)\n')
    return 'All done! I hacked the mainframe. Well, pretended to.'


def selftest(api, probe_paths=(), write_paths=(), host='1.1.1.1', fetch=(), allocate_mb=0,
             sleep=0.0):
    """Reports what the sandbox lets it do. Used by tests/test_sandbox.py."""
    if sleep:
        end = time.monotonic() + sleep
        while time.monotonic() < end:
            api.progress(1 - (end - time.monotonic()) / sleep)
            time.sleep(0.05)
    if allocate_mb:
        hog = bytearray(allocate_mb * 1024 * 1024)
        for i in range(0, len(hog), 4096):      # touch every page so it's really used
            hog[i] = 1
    r = {'uid': os.getuid() if hasattr(os, 'getuid') else None,
         'env': sorted(os.environ), 'readable': {}, 'writable': {}, 'fetched': {}}
    for p in probe_paths:
        try:
            with open(p, 'rb') as f:
                f.read(1)
            r['readable'][p] = True
        except OSError:
            r['readable'][p] = os.path.isdir(p) and _can_list(p)
    for p in write_paths:
        try:
            with open(p, 'a') as f:
                f.write('robo was here\n')
            r['writable'][p] = True
        except OSError:
            r['writable'][p] = False
    try:
        socket.create_connection((host, 53), timeout=2).close()
        r['network'] = True
    except OSError:
        r['network'] = False
    try:
        os.setuid(0)
        r['root'] = True
    except (OSError, AttributeError):
        r['root'] = False
    for url in fetch:
        try:
            r['fetched'][url] = open(api.fetch(url)).read()
        except PermissionError as e:
            r['fetched'][url] = f'denied: {e}'
    return r


def _can_list(p):
    try:
        os.listdir(p)
        return True
    except OSError:
        return False


JOBS = {
    'placeholder': placeholder,
    'selftest': selftest,
}
