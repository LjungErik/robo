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
import re
import shutil
import subprocess
import sys
import time
import zlib

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
PDF_PAGES_DIR = 'pdf-pages'                   # scratch folder for rendered PDF pages
SERVER = {'name': 'robo', 'version': '1.0'}

INSTRUCTIONS = """\
These are your only tools: you work in a sandboxed folder.
  input/    files the user let you READ (read-only)
  files/    COPIES of what the user let you CHANGE; edit them in place. The user
            reviews every change before it is applied to the real files.
  files/results/  put NEW things you make for the user here (reports, notes...)
Everything else in the folder is scratch space. There is no internet access.
PDF files: read them with read_pdf (text), or look_at_pdf_page (a picture of a page,
for scanned PDFs, charts and tables)."""


def _tool(name, description, props, required=()):
    return {'name': name, 'description': description,
            'inputSchema': {'type': 'object', 'properties': props,
                            'required': list(required), 'additionalProperties': False}}


TOOLS = [
    _tool('list_files', 'List the files and folders under a path (default: everything).',
          {'path': {'type': 'string', 'description': 'Folder, relative to the work folder'},
           'depth': {'type': 'integer', 'description': 'How deep to go (default 3)'}}),
    _tool('read_file', 'Read a text file (PDFs are read as text too). Long files: use '
          'offset/limit (in characters).',
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
    _tool('read_pdf', 'Read the text of a PDF file, page by page. Long PDFs: ask for a few '
          'pages at a time with first_page / last_page. Tells you how many pages there are.',
          {'path': {'type': 'string'},
           'first_page': {'type': 'integer', 'description': 'default 1'},
           'last_page': {'type': 'integer', 'description': 'default: the last page'},
           'offset': {'type': 'integer', 'description': 'characters to skip (long pages)'}},
          ['path']),
    _tool('look_at_pdf_page', 'Look at one page of a PDF as a picture: for scanned PDFs '
          '(no text), charts, tables and layouts.',
          {'path': {'type': 'string'}, 'page': {'type': 'integer', 'description': 'default 1'}},
          ['path']),
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
    if raw.startswith(b'%PDF'):
        return read_pdf(path, offset=offset)
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


# ---------------------------------------------------------------- PDF
def _tool_path(name):
    """A command-line program, if it is installed (poppler-utils: pdftotext ...)."""
    return shutil.which(name, path='/usr/bin:/bin:/usr/local/bin')


def _pdf_path(path):
    p = _path(path, must_exist=True)
    if os.path.isdir(p):
        raise ToolError(f'{path} is a folder; use list_files')
    with open(p, 'rb') as f:
        if b'%PDF' not in f.read(1024):
            raise ToolError(f'{path} is not a PDF file')
    return p


def _pdf_page_count(p):
    tool = _tool_path('pdfinfo')
    if tool:
        try:
            r = subprocess.run([tool, p], capture_output=True, timeout=30,
                               stdin=subprocess.DEVNULL)
            m = re.search(rb'^Pages:\s+(\d+)', r.stdout, re.M)
            if m:
                return int(m.group(1))
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        from pypdf import PdfReader               # if the system has it
        return len(PdfReader(p).pages)
    except Exception:
        pass
    with open(p, 'rb') as f:
        data = f.read()
    return len(re.findall(rb'/Type\s*/Page(?![a-zA-Z])', data)) or None


def _pdf_text_pdftotext(p, first, last):
    tool = _tool_path('pdftotext')
    if not tool:
        return None
    cmd = [tool, '-layout', '-enc', 'UTF-8', '-f', str(first)]
    if last:
        cmd += ['-l', str(last)]
    try:
        r = subprocess.run(cmd + [p, '-'], capture_output=True, timeout=COMMAND_TIMEOUT,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    pages = r.stdout.decode('utf-8', 'replace').split('\f')
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def _pdf_text_pypdf(p, first, last):
    try:
        from pypdf import PdfReader
    except Exception:
        return None
    try:
        reader = PdfReader(p)
        end = min(last or len(reader.pages), len(reader.pages))
        return [(reader.pages[i].extract_text() or '') for i in range(first - 1, end)]
    except Exception:
        return None


_PDF_ESCAPES = {b'n': b'\n', b'r': b'\r', b't': b'\t', b'b': b'\b', b'f': b'\f',
                b'(': b'(', b')': b')', b'\\': b'\\'}


def _pdf_literal(data, i):
    """Read a (literal string) starting just after its '('. -> (bytes, next index)."""
    out, depth = bytearray(), 1
    while i < len(data):
        c = data[i:i + 1]
        if c == b'\\':
            nxt = data[i + 1:i + 2]
            if nxt in _PDF_ESCAPES:
                out += _PDF_ESCAPES[nxt]
                i += 2
            elif nxt.isdigit():
                m = re.match(rb'[0-7]{1,3}', data[i + 1:i + 4])
                out.append(int(m.group(0), 8) & 0xFF)
                i += 1 + len(m.group(0))
            else:
                i += 2
            continue
        if c == b'(':
            depth += 1
        elif c == b')':
            depth -= 1
            if depth == 0:
                return bytes(out), i + 1
        out += c
        i += 1
    return bytes(out), i


def _pdf_decode(raw):
    if raw.startswith(b'\xfe\xff'):
        return raw[2:].decode('utf-16-be', 'replace')
    return raw.decode('latin-1')


_PDF_SHOW = {b'Tj', b'TJ', b"'", b'"'}
_PDF_NEWLINE = {b'T*', b'Td', b'TD', b'Tm', b'ET', b"'", b'"'}
_PDF_TOKEN = re.compile(rb"\s+|%[^\r\n]*|\(|<<|>>|<[0-9A-Fa-f\s]*>|\[|\]|/[^\s()<>\[\]{}/%]*"
                        rb"|[-+.0-9]+|[A-Za-z*'\"]+|.", re.S)


def _pdf_hex(token):
    hexs = re.sub(rb'\s', b'', token[1:-1])
    try:
        raw = bytes.fromhex((hexs + b'0' * (len(hexs) % 2)).decode('ascii'))
    except ValueError:
        return ''
    text = _pdf_decode(raw)
    # 2-byte font codes (CID fonts) can't be read without the font: skip the gibberish
    return text if all(ch.isprintable() or ch.isspace() for ch in text) else ''


def _pdf_content_text(content):
    """Text shown by Tj / TJ / ' / " in one content stream (good enough for simple PDFs)."""
    out, pending, i = [], [], 0
    while i < len(content):
        if content[i:i + 1] == b'(':
            s, i = _pdf_literal(content, i + 1)
            pending.append(_pdf_decode(s))
            continue
        m = _PDF_TOKEN.match(content, i)
        tok, i = m.group(0), m.end()
        if tok[:1] == b'<' and tok[:2] != b'<<':
            pending.append(_pdf_hex(tok))
        elif tok[:1].isalpha() or tok in (b"'", b'"', b'T*'):
            if tok in _PDF_NEWLINE and out and not out[-1].endswith('\n'):
                out.append('\n')
            if tok in _PDF_SHOW:
                out.append(''.join(pending))
            pending = []                    # any other operator: its operands are used up
    return ''.join(out)


def _pdf_text_builtin(p, first, last):
    """Last resort without any PDF programs: pull the text out of the page streams.
    Works for simple PDFs; compressed object streams and odd fonts may come out empty."""
    with open(p, 'rb') as f:
        data = f.read()
    texts = []
    for m in re.finditer(rb'<<(.*?)>>\s*stream\r?\n', data, re.S):
        head, start = m.group(1), m.end()
        end = data.find(b'endstream', start)
        if end < 0:
            continue
        if re.search(rb'/(Type\s*/(XObject|XRef|ObjStm|Metadata)|Subtype\s*/Image|Length1)',
                     head):
            continue
        stream = data[start:end]
        if b'FlateDecode' in head:
            try:
                stream = zlib.decompressobj().decompress(stream)
            except zlib.error:
                continue
        elif b'/Filter' in head:
            continue
        if b'BT' not in stream:
            continue
        text = _pdf_content_text(stream).strip()
        if text:
            texts.append(text)
    # the page each stream belongs to isn't tracked: treat each content stream as a page
    return texts[first - 1:last or None]


def read_pdf(path, first_page=1, last_page=None, offset=0):
    p = _pdf_path(path)
    first = max(1, int(first_page or 1))
    last = int(last_page) if last_page else None
    if last is not None and last < first:
        raise ToolError('last_page is before first_page')
    total = _pdf_page_count(p)
    if total and first > total:
        raise ToolError(f'{path} has only {total} pages')
    note = ''
    for extract in (_pdf_text_pdftotext, _pdf_text_pypdf, _pdf_text_builtin):
        pages = extract(p, first, last)
        if pages is not None and (extract is not _pdf_text_builtin or pages):
            if extract is _pdf_text_builtin:
                note = ('(No PDF reader is installed, so this is a rough extraction: the '
                        'text order or page breaks may be off.)\n')
            break
    else:
        pages = []
    parts = [f'--- page {first + i} ---\n{t.rstrip()}' for i, t in enumerate(pages)]
    text = '\n\n'.join(parts)
    if not text.strip() or not any(t.strip() for t in pages):
        if _tool_path('pdftoppm'):
            return (f'{path}: no text found on these pages (it may be scanned pictures). '
                    'Use look_at_pdf_page to look at the pages instead.')
        return (f'{path}: no text found on these pages. It may be scanned pictures, or use '
                'a kind of compression the built-in reader can\'t open (installing '
                'poppler-utils on this computer would help).')
    offset = max(0, int(offset or 0))
    chunk = text[offset:offset + MAX_READ]
    shown_last = first + len(pages) - 1
    header = f'{path}: {total or "?"} pages, showing {first}-{shown_last}\n{note}'
    if offset + MAX_READ < len(text):
        chunk += f'\n... [more: read again with offset={offset + MAX_READ}]'
    elif total and shown_last < total:
        chunk += f'\n... [pages {shown_last + 1}-{total} left: read_pdf with ' \
                 f'first_page={shown_last + 1}]'
    return header + chunk


def look_at_pdf_page(path, page=1):
    p = _pdf_path(path)
    page = max(1, int(page or 1))
    tool = _tool_path('pdftoppm')
    if not tool:
        raise ToolError('no PDF page renderer is installed here (poppler-utils); use '
                        'read_pdf for the text instead')
    out_dir = os.path.join(ROOT, PDF_PAGES_DIR)
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, f'page-{page}')
    for dpi in (110, 72, 50):
        try:
            r = subprocess.run([tool, '-png', '-r', str(dpi), '-f', str(page), '-l', str(page),
                                '-singlefile', p, stem], capture_output=True,
                               timeout=COMMAND_TIMEOUT, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            raise ToolError('could not draw that page')
        png = stem + '.png'
        if r.returncode != 0 or not os.path.isfile(png):
            raise ToolError(f'could not draw page {page}: '
                            + r.stderr.decode('utf-8', 'replace').strip()[:300])
        if os.path.getsize(png) <= MAX_IMAGE_BYTES:
            with open(png, 'rb') as f:
                return Image(f.read(), 'image/png')
    raise ToolError(f'page {page} is too big to look at')


def report_progress(note, fraction=None):
    _event(tool='report_progress', note=str(note)[:300],
           fraction=None if fraction is None else max(0.0, min(1.0, float(fraction))))
    return 'ok'


HANDLERS = {'list_files': list_files, 'read_file': read_file, 'write_file': write_file,
            'edit_file': edit_file, 'move': move, 'delete': delete, 'make_folder': make_folder,
            'run_command': run_command, 'look_at_image': look_at_image,
            'read_pdf': read_pdf, 'look_at_pdf_page': look_at_pdf_page,
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
