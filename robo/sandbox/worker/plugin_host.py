"""Runs one Robo plugin, inside the sandbox (robo/plugins/runner.py starts it).

The plugin's folder is at ./plugin (read-only); ./ is its own writable folder.
Talks to Robo with JSON lines on stdin / stdout:

    Robo -> host   {"type": "start", "manifest": {...}}
                   {"type": "invoke", "rid": 1, "kind": "command"|"tool"|"menu"|"event",
                    "name": "c0", "text": "...", "args": {...}}
                   {"type": "reply", "id": 3, "value": ..., "error": null}
                   {"type": "stop"}
    host -> Robo   {"type": "ready", "commands": [...], "tools": [...], "menus": [...]}
                   {"type": "result", "rid": 1, "value": "...", "error": null}
                   {"type": "call", "id": 3, "method": "say", "args": {...}}
                   {"type": "error", "message": "..."}
print() in a plugin goes to its log (stderr), not to Robo.
"""
import importlib.util
import json
import os
import sys
import threading
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import robo_plugin  # noqa: E402

STOP_GRACE = 2.0


def _run(fn, *args, **kw):
    try:
        return fn(*args, **kw), None
    except robo_plugin.Stopped:
        return None, 'stopped'
    except Exception as e:                 # noqa: BLE001 - report to Robo, keep running
        traceback.print_exc()
        return None, f'{type(e).__name__}: {e}'


def _load(entry):
    folder = os.path.abspath('plugin')
    sys.path.insert(0, folder)
    spec = importlib.util.spec_from_file_location('robo_plugin_main', os.path.join(folder, entry))
    module = importlib.util.module_from_spec(spec)
    sys.modules['robo_plugin_main'] = module
    spec.loader.exec_module(module)


def main():
    link = robo_plugin._Link(sys.stdout)
    sys.stdout = sys.stderr                # print() goes to the log
    p = robo_plugin.plugin
    p._link = link
    first = sys.stdin.readline()
    try:
        start = json.loads(first)
    except ValueError:
        start = {}
    p.manifest = start.get('manifest') or {}
    entry = os.path.basename(p.manifest.get('entry') or 'plugin.py')
    try:
        _load(entry)
    except Exception as e:                 # noqa: BLE001
        traceback.print_exc()
        link.send({'type': 'error', 'message': f'{type(e).__name__}: {e}'})
        return 1

    link.send({'type': 'ready',
               'commands': [{'id': k, 'phrases': list(v[0])} for k, v in p.commands.items()],
               'tools': [{'name': k, 'description': v[0], 'params': v[1]}
                         for k, v in p.tools.items()],
               'menus': [{'id': k, 'label': v[0]} for k, v in p.menus.items()]})

    def spawn(fn, *args):
        threading.Thread(target=_run, args=(fn,) + args, daemon=True).start()

    for fn in p.events.get('start', ()):
        spawn(fn)
    for fn in p.loops:
        spawn(fn)

    def invoke(msg):
        kind, name = msg.get('kind'), msg.get('name')
        if kind == 'command' and name in p.commands:
            value, error = _run(p.commands[name][1], msg.get('text', ''))
        elif kind == 'tool' and name in p.tools:
            value, error = _run(p.tools[name][2], **(msg.get('args') or {}))
        elif kind == 'menu' and name in p.menus:
            value, error = _run(p.menus[name][1])
        elif kind == 'event':
            value, error = None, None
            for fn in p.events.get(name, ()):
                _run(fn, *(msg.get('args') or ()))
        else:
            value, error = None, f'no {kind} called {name}'
        link.send({'type': 'result', 'rid': msg.get('rid'),
                   'value': None if value is None else str(value), 'error': error})

    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        kind = msg.get('type')
        if kind == 'reply':
            link.resolve(msg.get('id'), msg.get('value'), msg.get('error'))
        elif kind == 'invoke':
            threading.Thread(target=invoke, args=(msg,), daemon=True).start()
        elif kind == 'stop':
            break
    p._stopping.set()
    link.fail_all('stopped')
    done = [threading.Thread(target=_run, args=(fn,), daemon=True)
            for fn in p.events.get('stop', ())]
    for t in done:
        t.start()
    for t in done:
        t.join(STOP_GRACE)
    return 0


if __name__ == '__main__':
    sys.exit(main())
