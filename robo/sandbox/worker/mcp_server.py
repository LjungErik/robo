"""Robo's tools for an AI agent, served over MCP. Runs INSIDE the sandbox.

An agent task (robo/tasks/agent_task.py) starts the agent's CLI (Claude Code)
OUTSIDE the sandbox with all of its own tools switched off, and gives it this
server as its only tools. The CLI launches this server through the sandbox
backend, so every file the agent reads or writes and every command it runs
happens in here: in the task's work folder, with no network and nothing of
yours except what you granted (read-only inputs, and copies of what it may
change, which you review afterwards).

    stdin / stdout   MCP (JSON-RPC 2.0, one message per line)
    .robo/events.jsonl  what it did, one line per tool call (Robo reads it for progress)

Standard library only, like the rest of the worker.
"""
import base64
import json
import os
import subprocess
import sys
import time

ROOT = os.path.realpath(os.getcwd())          # the task's work folder (/work in the sandbox)
if '--root' in sys.argv:                      # (tests run it without a sandbox)
    ROOT = os.path.realpath(sys.argv[sys.argv.index('--root') + 1])
    os.chdir(ROOT)
EVENTS = os.path.join(ROOT, '.robo', 'events.jsonl')
MAX_READ = 200_000                            # characters per read_file
MAX_OUTPUT = 20_000                           # characters of command output
COMMAND_TIMEOUT = 120
MAX_IMAGE_BYTES = 4_000_000
IMAGE_TYPES = {b'\x89PNG': 'image/png', b'\xff\xd8\xff': 'image/jpeg'}
SERVER = {'name': 'robo', 'version': '1.0'}

INSTRUCTIONS = """\
These are your only tools: you work in a sandboxed folder.
  input/    files the user let you READ (read-only)
  files/    COPIES of what the user let you CHANGE; edit them in place. The user
            reviews every change before it is applied to the real files.
  files/results/  put NEW things you make for the user here (reports, notes...)
Everything else in the folder is scratch space. There is no internet access."""


def _tool(name, description, props, required=()):
    return {'name': name, 'description': description,
            'inputSchema': {'type': 'object', 'properties': props,
                            'required': list(required), 'additionalProperties': False}}


TOOLS = [
    _tool('list_files', 'List the files and folders under a path (default: everything).',
          {'path': {'type': 'string', 'description': 'Folder, relative to the work folder'},
           'depth': {'type': 'integer', 'description': 'How deep to go (default 3)'}}),
    _tool('read_file', 'Read a text file. Long files: use offset/limit (in characters).',
          {'path': {'type': 'string'}, 'offset': {'type': 'integer'},
           'limit': {'type': 'integer'}}, ['path']),
    _tool('write_file', 'Create or overwrite a text file (only under files/ or scratch space).',
          {'path': {'type': 'string'}, 'content': {'type': 'string'}}, ['path', 'content']),
    _tool('edit_file', 'Replace one exact piece of text in a file with another.',
          {'path': {'type': 'string'}, 'old': {'type': 'string'}, 'new': {'type': 'string'}},
          ['path', 'old', 'new']),
    _tool('move', 'Move or rename a file or folder.',
          {'source': {'type': 'string'}, 'target': {'type': 'string'}}, ['source', 'target']),
    _tool('delete', 'Delete a file or an empty folder.', {'path': {'type': 'string'}}, ['path']),
    _tool('make_folder', 'Create a folder (and its parents).', {'path': {'type': 'string'}},
          ['path']),
    _tool('run_command', 'Run a shell command in the work folder (sandboxed: no internet, '
          'only this folder). Python 3 and the usual command-line tools are available.',
          {'command': {'type': 'string'},
           'timeout': {'type': 'integer', 'description': f'seconds, max {COMMAND_TIMEOUT}'}},
          ['command']),
    _tool('look_at_image', 'Look at a PNG or JPEG picture in the work folder (for example a '
          'preview you drew).', {'path': {'type': 'string'}}, ['path']),
    _tool('report_progress', 'Tell the user (through Robo) what you are doing now.',
          {'note': {'type': 'string'},
           'fraction': {'type': 'number', 'description': '0..1, how far along you think you are'}},
          ['note']),
]


class ToolError(Exception):
    pass


def _path(rel, must_exist=False):
    """A path inside the work folder (no escaping with .. or absolute paths)."""
    if not isinstance(rel, str):
        raise ToolError('path must be a string')
    rel = rel.strip() or '.'
    if rel.startswith('/work/'):
        rel = rel[len('/work/'):]
    p = os.path.realpath(os.path.join(ROOT, rel))
    if p != ROOT and not p.startswith(ROOT + os.sep):
        raise ToolError(f'{rel} is outside the work folder')
    if p.startswith(os.path.join(ROOT, '.robo')):
        raise ToolError('.robo is Robo\'s own folder')
    if must_exist and not os.path.exists(p):
        raise ToolError(f'{rel} does not exist')
    return p


def _rel(p):
    return os.path.relpath(p, ROOT)


def _event(**fields):
    try:
        os.makedirs(os.path.dirname(EVENTS), exist_ok=True)
        with open(EVENTS, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'time': time.time(), **fields}) + '\n')
    except OSError:
        pass


# ---------------------------------------------------------------- tools
def list_files(path='.', depth=3):
    top = _path(path, must_exist=True)
    if os.path.isfile(top):
        return f'{_rel(top)} ({os.path.getsize(top)} bytes)'
    lines, count = [], 0
    base_depth = top.count(os.sep)
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames[:] = sorted(d for d in dirnames if d != '.robo')
        level = dirpath.count(os.sep) - base_depth
        if level >= max(1, int(depth)):
            dirnames[:] = []
        for d in dirnames:
            lines.append(_rel(os.path.join(dirpath, d)) + '/')
        for name in sorted(filenames):
            p = os.path.join(dirpath, name)
            try:
                lines.append(f'{_rel(p)} ({os.path.getsize(p)} bytes)')
            except OSError:
                lines.append(_rel(p))
            count += 1
            if count > 2000:
                lines.append('... (more files not shown)')
                return '\n'.join(sorted(lines))
    return '\n'.join(sorted(lines)) or '(empty)'


def read_file(path, offset=0, limit=MAX_READ):
    p = _path(path, must_exist=True)
    if os.path.isdir(p):
        raise ToolError(f'{path} is a folder; use list_files')
    with open(p, 'rb') as f:
        raw = f.read(MAX_READ * 4 + int(offset or 0) * 4)
    if b'\0' in raw[:4096]:
        return f'{path} looks like a binary file ({os.path.getsize(p)} bytes); ' \
               'use run_command to inspect it'
    text = raw.decode('utf-8', 'replace')
    offset, limit = max(0, int(offset or 0)), max(1, min(int(limit or MAX_READ), MAX_READ))
    chunk = text[offset:offset + limit]
    if offset + limit < len(text) or os.path.getsize(p) > len(raw):
        chunk += f'\n... [more: read again with offset={offset + limit}]'
    return chunk


def write_file(path, content):
    p = _path(path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(content)
    return f'wrote {_rel(p)} ({len(content)} characters)'


def edit_file(path, old, new):
    p = _path(path, must_exist=True)
    with open(p, encoding='utf-8') as f:
        text = f.read()
    n = text.count(old)
    if n != 1:
        raise ToolError(f'the text to replace was found {n} times (it must be exactly once)')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text.replace(old, new, 1))
    return f'edited {_rel(p)}'


def move(source, target):
    src, dst = _path(source, must_exist=True), _path(target)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.replace(src, dst)
    return f'moved {_rel(src)} to {_rel(dst)}'


def delete(path):
    p = _path(path, must_exist=True)
    if p == ROOT:
        raise ToolError('can not delete the work folder')
    if os.path.isdir(p):
        os.rmdir(p)
    else:
        os.remove(p)
    return f'deleted {_rel(p)}'


def make_folder(path):
    p = _path(path)
    os.makedirs(p, exist_ok=True)
    return f'made {_rel(p)}/'


def run_command(command, timeout=60):
    timeout = max(1, min(int(timeout or 60), COMMAND_TIMEOUT))
    try:
        r = subprocess.run(['/bin/sh', '-c', command], cwd=ROOT, capture_output=True,
                           stdin=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ToolError(f'the command took longer than {timeout} s and was stopped')
    out = (r.stdout + r.stderr).decode('utf-8', 'replace')
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + f'\n... [{len(out) - MAX_OUTPUT} more characters cut]'
    return f'exit code {r.returncode}\n{out}'


class Image:
    def __init__(self, data, mime):
        self.data, self.mime = data, mime


def look_at_image(path):
    p = _path(path, must_exist=True)
    if os.path.getsize(p) > MAX_IMAGE_BYTES:
        raise ToolError(f'{path} is too big to look at (max {MAX_IMAGE_BYTES // 1_000_000} MB)')
    with open(p, 'rb') as f:
        data = f.read()
    mime = next((m for magic, m in IMAGE_TYPES.items() if data.startswith(magic)), None)
    if mime is None:
        raise ToolError(f'{path} is not a PNG or JPEG picture')
    return Image(data, mime)


def report_progress(note, fraction=None):
    _event(tool='report_progress', note=str(note)[:300],
           fraction=None if fraction is None else max(0.0, min(1.0, float(fraction))))
    return 'ok'


HANDLERS = {'list_files': list_files, 'read_file': read_file, 'write_file': write_file,
            'edit_file': edit_file, 'move': move, 'delete': delete, 'make_folder': make_folder,
            'run_command': run_command, 'look_at_image': look_at_image,
            'report_progress': report_progress}


# ---------------------------------------------------------------- MCP
def handle(msg):
    """One JSON-RPC message -> response dict (or None for notifications)."""
    method, mid = msg.get('method'), msg.get('id')
    if mid is None:
        return None                                   # notifications need no answer
    if method == 'initialize':
        version = (msg.get('params') or {}).get('protocolVersion') or '2025-06-18'
        result = {'protocolVersion': version, 'capabilities': {'tools': {}},
                  'serverInfo': SERVER, 'instructions': INSTRUCTIONS}
    elif method == 'ping':
        result = {}
    elif method == 'tools/list':
        result = {'tools': TOOLS}
    elif method == 'tools/call':
        params = msg.get('params') or {}
        name, args = params.get('name'), params.get('arguments') or {}
        fn = HANDLERS.get(name)
        if fn is None:
            return _error(mid, -32602, f'unknown tool {name}')
        if name != 'report_progress':
            _event(tool=name, args={k: (v if len(str(v)) < 200 else str(v)[:200] + '...')
                                    for k, v in args.items()})
        try:
            text, is_error = fn(**args), False
        except ToolError as e:
            text, is_error = str(e), True
        except TypeError as e:
            text, is_error = f'bad arguments: {e}', True
        except OSError as e:
            text, is_error = f'{type(e).__name__}: {e.strerror or e}', True
        if isinstance(text, Image):
            content = [{'type': 'image', 'data': base64.b64encode(text.data).decode('ascii'),
                        'mimeType': text.mime}]
        else:
            content = [{'type': 'text', 'text': str(text)}]
        result = {'content': content, 'isError': is_error}
    else:
        return _error(mid, -32601, f'unknown method {method}')
    return {'jsonrpc': '2.0', 'id': mid, 'result': result}


def _error(mid, code, message):
    return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': code, 'message': message}}


def main():
    out = os.fdopen(os.dup(1), 'w', buffering=1)
    os.dup2(2, 1)                                     # stray prints go to stderr
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            out.write(json.dumps(_error(None, -32700, 'parse error')) + '\n')
            continue
        batch = msg if isinstance(msg, list) else [msg]
        for m in batch:
            if isinstance(m, dict):
                reply = handle(m)
                if reply is not None:
                    out.write(json.dumps(reply) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
