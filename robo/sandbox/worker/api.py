"""What a job can use inside the sandbox. Standard library only.

    api.progress(0.5)              how far along it is (0..1)
    api.log('found 3 files')       goes to Robo's log
    api.inputs['notes.txt']        path of a file / folder you let it read
    api.files['report']            path of its copy of something you let it change
    api.fetch('https://...')       download (only from hosts you allowed); returns a path
    api.work_dir                   its own folder: write results here
"""
import json
import os


class Channel:
    def __init__(self, inp, out):
        self.inp, self.out = inp, out
        self._next_id = 0

    def send(self, msg):
        self.out.write(json.dumps(msg) + '\n')
        self.out.flush()

    def read(self):
        line = self.inp.readline()
        return json.loads(line) if line else None

    def request(self, op, **fields):
        self._next_id += 1
        rid = self._next_id
        self.send({'type': 'request', 'id': rid, 'op': op, **fields})
        while True:
            msg = self.read()
            if msg is None:
                raise ConnectionError('Robo went away')
            if msg.get('type') == 'reply' and msg.get('id') == rid:
                return msg


class TaskAPI:
    def __init__(self, chan, inputs, files):
        self._chan = chan
        self.work_dir = os.getcwd()
        self.inputs = {k: os.path.join(self.work_dir, v) for k, v in inputs.items()}
        self.files = {k: os.path.join(self.work_dir, v) for k, v in files.items()}

    def progress(self, value):
        self._chan.send({'type': 'progress', 'value': max(0.0, min(1.0, float(value)))})

    def log(self, text):
        self._chan.send({'type': 'log', 'text': str(text)[:2000]})

    def fetch(self, url):
        """Download `url` (via Robo, who checks you allowed it). Returns the file's path."""
        reply = self._chan.request('fetch', url=url)
        if not reply.get('ok'):
            raise PermissionError(reply.get('error', 'refused'))
        return os.path.join(self.work_dir, reply['value'])

