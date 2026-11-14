"""The library a Robo plugin uses: `from robo_plugin import plugin`.

A plugin runs in its own sandboxed process (plugin_host.py). It can't touch
your files, the network or your desktop; everything it does goes through
Robo, who checks the permissions you gave it (plugin.json "permissions").

    from robo_plugin import plugin

    @plugin.command('flip a coin', 'heads or tails')     # you say it (or type it)
    def flip(text):
        return 'Heads!'                                  # Robo says the answer

    @plugin.tool('roll_dice', 'Roll dice', sides='number of sides')   # his AI brain may use it
    def roll(sides=6):
        return str(random.randint(1, int(sides)))

    @plugin.menu('🎲  Roll a dice')                       # in his right-click menu
    def menu():
        plugin.say(f'I rolled a {random.randint(1, 6)}!')

    @plugin.background                                  # runs while the plugin is on
    def loop():
        while plugin.wait(60):                           # False once Robo stops the plugin
            ...

Handlers run on their own threads, so they may block (wait for the AI,
hold a key down for a second...). Everything here is plain Python
standard library; /work is the plugin's own folder for files it keeps.
"""
import itertools
import json
import sys
import threading
import time

API_VERSION = 1


class RoboError(Exception):
    """Robo said no (a missing permission, the screen isn't shared...) or failed."""


class Stopped(RoboError):
    """The plugin is being stopped (reloaded or switched off)."""


class _Link:
    """JSON lines to and from Robo (stdout is reserved for this)."""

    def __init__(self, out):
        self.out = out
        self.lock = threading.Lock()
        self.ids = itertools.count(1)
        self.waiting = {}

    def send(self, msg):
        line = json.dumps(msg) + '\n'
        with self.lock:
            self.out.write(line)
            self.out.flush()

    def call(self, method, timeout=600.0, **args):
        rid = next(self.ids)
        slot = self.waiting[rid] = [threading.Event(), None, None]
        self.send({'type': 'call', 'id': rid, 'method': method, 'args': args})
        if not slot[0].wait(timeout):
            self.waiting.pop(rid, None)
            raise RoboError(f'Robo did not answer {method}')
        self.waiting.pop(rid, None)
        if slot[2]:
            raise (Stopped if slot[2] == 'stopped' else RoboError)(slot[2])
        return slot[1]

    def resolve(self, rid, value=None, error=None):
        slot = self.waiting.get(rid)
        if slot:
            slot[1], slot[2] = value, error
            slot[0].set()

    def fail_all(self, error):
        for slot in list(self.waiting.values()):
            slot[2] = error
            slot[0].set()


class _Screen:
    """Your screen, while you're showing it to Robo (permission "screen")."""

    def __init__(self, p):
        self._p = p

    @property
    def shared(self):
        return bool(self._p._call('screen.shared'))

    def ask(self):
        """Ask you to share your screen or a window (GNOME's picker). True if you did."""
        return bool(self._p._call('screen.ask', timeout=180))

    def grab(self):
        """The latest picture of what you're showing, as a PNG file path (in /work)."""
        return self._p._call('screen.grab')


class _Camera:
    """Your camera (permission "camera"). Robo shows that it's taking a picture."""

    def __init__(self, p):
        self._p = p

    def snapshot(self):
        """Take a picture: a PNG file path (in /work)."""
        return self._p._call('camera.snapshot', timeout=30)


class _Input:
    """Keyboard and mouse (permission "input"). Nothing works until you allow it in
    GNOME's dialog (start()); "stop", a click on Robo, or his menu ends it.

    Keys are names: 'w', 'space', 'Return', 'Escape', 'ctrl', 'shift', 'alt',
    'Up', 'F5'... Combos are joined with '+': 'ctrl+s'. Mouse buttons: left,
    right, middle."""

    MAX_HOLD = 5.0

    def __init__(self, p):
        self._p = p

    @property
    def active(self):
        return bool(self._p._call('input.active'))

    def start(self, why=''):
        """Ask to use your keyboard and mouse. True once you allowed it."""
        return bool(self._p._call('input.start', why=why, timeout=180))

    def stop(self):
        self._p._call('input.stop')

    def down(self, key):
        self._p._call('input.key', key=key, down=True)

    def up(self, key):
        self._p._call('input.key', key=key, down=False)

    def press(self, combo, hold=0.05):
        """Press keys together ('ctrl+s'), hold them `hold` seconds, let go."""
        keys = [k for k in combo.split('+') if k] if combo != '+' else ['plus']
        hold = max(0.0, min(float(hold), self.MAX_HOLD))
        pressed = []
        try:
            for k in keys:
                self.down(k)
                pressed.append(k)
            self._p.wait(hold)
        finally:
            for k in reversed(pressed):
                try:
                    self.up(k)
                except RoboError:
                    pass

    def hold(self, key, seconds):
        self.press(key, hold=seconds)

    def type(self, text, delay=0.03):
        for ch in str(text)[:500]:
            self.press({' ': 'space', '\n': 'Return', '\t': 'Tab'}.get(ch, ch), hold=delay)

    def move(self, dx, dy):
        """Move the mouse by (dx, dy) pixels (in a game: look around)."""
        self._p._call('input.move', dx=float(dx), dy=float(dy))

    def click(self, button='left', hold=0.05):
        hold = max(0.0, min(float(hold), self.MAX_HOLD))
        self._p._call('input.button', button=button, down=True)
        try:
            self._p.wait(hold)
        finally:
            self._p._call('input.button', button=button, down=False)

    def scroll(self, steps):
        self._p._call('input.scroll', steps=int(steps))

    def release_all(self):
        self._p._call('input.release')


class _AI:
    """Robo's AI brain (permission "ai"; it uses your plan, like chatting does)."""

    def __init__(self, p):
        self._p = p

    def ask(self, prompt, image=None):
        """Ask a question, optionally about a picture (a path from grab/snapshot)."""
        return self._p._call('ai.ask', prompt=str(prompt), image=image, timeout=300)


class Plugin:
    def __init__(self):
        self.commands = {}           # id -> (phrases, handler)
        self.tools = {}              # name -> (description, params, handler)
        self.menus = {}              # id -> (label, handler)
        self.events = {}             # name -> [handler]
        self.loops = []
        self.screen = _Screen(self)
        self.camera = _Camera(self)
        self.input = _Input(self)
        self.ai = _AI(self)
        self.manifest = {}
        self._link = None
        self._stopping = threading.Event()

    # ------------------------------------------------------------ declaring
    def command(self, *phrases):
        """Things you can say to Robo that this plugin answers. The handler gets
        what you said and returns what Robo says (or None to say nothing)."""
        def wrap(fn):
            self.commands[f'c{len(self.commands)}'] = (tuple(p.lower() for p in phrases), fn)
            return fn
        return wrap

    def tool(self, name, description, **params):
        """Something his AI brain may decide to do while chatting with you.
        params: name -> what it means. The handler returns a short result."""
        def wrap(fn):
            self.tools[name] = (description, params, fn)
            return fn
        return wrap

    def menu(self, label):
        def wrap(fn):
            self.menus[f'm{len(self.menus)}'] = (label, fn)
            return fn
        return wrap

    def on(self, event):
        """'start', 'stop', 'input_stopped' (you took the controls back)."""
        def wrap(fn):
            self.events.setdefault(event, []).append(fn)
            return fn
        return wrap

    def background(self, fn):
        self.loops.append(fn)
        return fn

    # ------------------------------------------------------------ doing
    @property
    def running(self):
        return not self._stopping.is_set()

    def wait(self, seconds):
        """Sleep, but wake up if the plugin is stopped. True = keep going."""
        return not self._stopping.wait(max(0.0, seconds))

    def say(self, text, mood='happy'):
        """Robo says it out loud (after he finishes what he's saying)."""
        self._call('say', text=str(text), mood=mood)

    def emote(self, action):
        """wave, cheer, hearts, laugh or dance."""
        self._call('emote', action=action)

    def log(self, *parts):
        print(*parts, file=sys.stderr, flush=True)

    def _call(self, method, timeout=600.0, **args):
        if self._link is None:
            raise RoboError('not running inside Robo')
        if self._stopping.is_set():        # (Robo lets go of any keys it still holds)
            raise Stopped('stopped')
        return self._link.call(method, timeout=timeout, **args)


plugin = Plugin()
