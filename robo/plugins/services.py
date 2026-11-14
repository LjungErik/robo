"""What plugins may ask Robo to do, and the permission check in front of it.

Every request from a plugin (robo_plugin.py: plugin.say, plugin.screen.grab,
plugin.input.press, plugin.ai.ask...) arrives here as `call(runner, id,
method, args)`. Requests in an area that needs a permission (screen, camera,
input, ai) are refused unless you granted it to that plugin. Answers go
back with runner.reply(); slow ones (the AI, GNOME's dialogs) answer later.

Keyboard and mouse ("input") are the touchy part, so:
  - GNOME asks you first (the RemoteDesktop portal) and shows that it's on;
  - Robo shows a banner, and only one plugin at a time may hold the controls;
  - "stop", clicking Robo, his menu, or the banner gives them back at once,
    and every key or button still held down is let go;
  - a plugin that stops, crashes or reloads lets go too.
"""
import logging
import os
import queue
import threading

from .manifest import PERMISSIONS

log = logging.getLogger(__name__)

EMOTES = ('wave', 'cheer', 'hearts', 'laugh', 'dance')
MAX_SAY = 500
MAX_PROMPT = 20_000
MAX_MOVE = 3000
PLUGIN_SYSTEM = ("You are the thinking part of a plugin for Robo, a little robot that "
                 "lives on the user's screen. Answer the request directly, briefly, and in "
                 "exactly the format it asks for. No markdown unless it asks for it.")


class Services:
    def __init__(self, robot, granted, input_control=None, camera=None, ai_backend=None):
        self.robot = robot                  # robo.core.companion.Companion
        self.granted = granted              # plugin id -> set of granted permissions
        self.input = input_control          # robo.platform.base.InputControl or None
        self.camera = camera                # robo.platform.base.Camera or None
        self.ai_backend = ai_backend        # () -> AgentBackend or None
        self.input_owner = None             # the runner holding keyboard and mouse
        self._held = set()                  # ('key', name) / ('button', name) held down
        self._input_waiting = None          # (runner, reply) while GNOME's dialog is up
        self._share_waiting = []            # (runner, reply) waiting for you to share
        self._ai_busy = set()               # plugin ids with a question out
        self._done = queue.Queue()          # finished background work: (fn, args)
        self.on_control_changed = None      # (holding: bool) -> None, for Robo's indicator

    # ------------------------------------------------------------ dispatch
    def call(self, runner, call_id, method, args):
        def reply(value=None, error=None):
            runner.reply(call_id, value, error)
        area = method.split('.', 1)[0]
        if area in PERMISSIONS and area not in self.granted(runner.id):
            reply(error=f'{runner.manifest.name} has no permission to use the {area} '
                        f'(see plugin.json "permissions")')
            return
        fn = getattr(self, '_' + method.replace('.', '_'), None)
        if fn is None or method.startswith('_'):
            reply(error=f'Robo does not know "{method}"')
            return
        try:
            fn(runner, args, reply)
        except (TypeError, ValueError) as e:
            reply(error=f'bad request {method}: {e}')
        except Exception as e:            # noqa: BLE001 - never let a plugin crash Robo
            log.exception('plugin %s: %s failed', runner.id, method)
            reply(error=f'{method} failed: {e}')

    def update(self, now):
        while True:
            try:
                fn, args = self._done.get_nowait()
            except queue.Empty:
                return
            fn(*args)

    def _later(self, fn, *args):
        """From a worker thread: run fn(*args) on the main thread (in update)."""
        self._done.put((fn, args))

    def _file(self, runner, name, data):
        """Put a picture in the plugin's folder; returns the path it sees."""
        folder = os.path.join(runner.data_dir, 'frames')
        os.makedirs(folder, exist_ok=True)
        tmp = os.path.join(folder, f'.{name}.tmp')
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, os.path.join(folder, name))
        return f'frames/{name}'

    # ------------------------------------------------------------ always allowed
    def _say(self, runner, args, reply):
        text = ' '.join(str(args.get('text') or '').split())[:MAX_SAY]
        if text:
            self.robot.conversation.announce(text, str(args.get('mood') or 'happy'))
        reply(True)

    def _emote(self, runner, args, reply):
        action = str(args.get('action') or '')
        if action not in EMOTES:
            reply(error=f'emote is one of {", ".join(EMOTES)}')
            return
        self.robot.emote(action)
        reply(True)

    # ------------------------------------------------------------ screen
    def _screen_shared(self, runner, args, reply):
        reply(bool(self.robot.seeing))

    def _screen_ask(self, runner, args, reply):
        if self.robot.seeing:
            reply(True)
            return
        if not self.robot.can_see_screen():
            reply(error="this computer can't share the screen with Robo")
            return
        self._share_waiting.append((runner, reply))
        self.robot.show_screen()

    def share_changed(self, seeing):
        waiting, self._share_waiting = self._share_waiting, []
        for _runner, reply in waiting:
            reply(bool(seeing))

    def _screen_grab(self, runner, args, reply):
        png = self.robot.look_at_screen()
        if png is None:
            reply(error="the screen isn't shared with Robo (plugin.screen.ask() first)")
            return
        reply(self._file(runner, 'screen.png', png))

    # ------------------------------------------------------------ camera
    def _camera_snapshot(self, runner, args, reply):
        if self.camera is None or self.camera.problem():
            reply(error=(self.camera.problem() if self.camera else None)
                  or 'there is no camera Robo can use')
            return
        self.robot.camera_flash()

        def done(png, error):
            if png:
                reply(self._file(runner, 'camera.png', png))
            else:
                reply(error=error or 'the camera gave no picture')
        self.camera.snapshot(done)

    # ------------------------------------------------------------ keyboard and mouse
    @property
    def controlling(self):
        return self.input_owner is not None and self.input is not None and self.input.active

    def _input_active(self, runner, args, reply):
        reply(self.controlling and self.input_owner is runner)

    def _input_start(self, runner, args, reply):
        if self.input is None or self.input.problem():
            reply(error=(self.input.problem() if self.input else None)
                  or "Robo can't use the keyboard and mouse here")
            return
        if self.controlling:
            if self.input_owner is runner:
                reply(True)
            else:
                reply(error=f'{self.input_owner.manifest.name} is using the controls')
            return
        if self._input_waiting is not None:
            reply(error='already asking you')
            return
        self._input_waiting = (runner, reply)
        why = ' '.join(str(args.get('why') or '').split())[:120]
        self.robot.conversation.announce(
            f"{runner.manifest.name} would like to use your keyboard and mouse"
            + (f' to {why}' if why else '') + '. Say stop any time to take them back.', 'happy')

        def started():
            waiting, self._input_waiting = self._input_waiting, None
            if waiting is None or waiting[0].proc is None:       # it went away meanwhile
                self.input.stop()
                return
            self.input_owner = waiting[0]
            log.info('plugin %s has the keyboard and mouse', runner.id)
            if self.on_control_changed:
                self.on_control_changed(True)
            waiting[1](True)

        def ended(reason):
            waiting, self._input_waiting = self._input_waiting, None
            if waiting is not None:
                waiting[1](error=f'not allowed: {reason}')
            self._released(reason)
        self.input.start(started, ended)

    def _check_owner(self, runner):
        if not self.controlling or self.input_owner is not runner:
            raise ValueError('it does not have the keyboard and mouse (input.start() first)')

    def _input_key(self, runner, args, reply):
        self._check_owner(runner)
        name, down = str(args.get('key') or ''), bool(args.get('down'))
        if not self.input.key(name, down):
            reply(error=f'unknown key {name!r}')
            return
        (self._held.add if down else self._held.discard)(('key', name))
        reply(True)

    def _input_button(self, runner, args, reply):
        self._check_owner(runner)
        name, down = str(args.get('button') or 'left'), bool(args.get('down'))
        if not self.input.button(name, down):
            reply(error=f'unknown mouse button {name!r}')
            return
        (self._held.add if down else self._held.discard)(('button', name))
        reply(True)

    def _input_move(self, runner, args, reply):
        self._check_owner(runner)
        dx = max(-MAX_MOVE, min(MAX_MOVE, float(args.get('dx') or 0)))
        dy = max(-MAX_MOVE, min(MAX_MOVE, float(args.get('dy') or 0)))
        self.input.move(dx, dy)
        reply(True)

    def _input_scroll(self, runner, args, reply):
        self._check_owner(runner)
        self.input.scroll(max(-20, min(20, int(args.get('steps') or 0))))
        reply(True)

    def _input_release(self, runner, args, reply):
        self._check_owner(runner)
        self._let_go()
        reply(True)

    def _input_stop(self, runner, args, reply):
        if self.input_owner is runner:
            self.stop_control('the plugin is done')
        reply(True)

    def _let_go(self):
        for kind, name in list(self._held):
            try:
                (self.input.key if kind == 'key' else self.input.button)(name, False)
            except Exception:              # noqa: BLE001
                pass
        self._held.clear()

    def stop_control(self, reason='you took the controls back'):
        """Give the keyboard and mouse back now (stop, a click, the menu, the banner)."""
        if self.input is None:
            return
        if self.input.active:
            self._let_go()
            self.input.stop()             # -> ended() -> _released()
        self._released(reason)

    def _released(self, reason):
        owner, self.input_owner = self.input_owner, None
        self._held.clear()
        if owner is not None:
            log.info('keyboard and mouse given back (%s)', reason)
            owner.event('input_stopped', reason)
            if self.on_control_changed:
                self.on_control_changed(False)

    # ------------------------------------------------------------ AI
    def _ai_ask(self, runner, args, reply):
        backend = self.ai_backend() if self.ai_backend else None
        if backend is None:
            reply(error="Robo's AI brain is off (Settings → AI brain)")
            return
        if runner.id in self._ai_busy:
            reply(error='one question at a time')
            return
        if not self.robot.within_budget():
            reply(error="today's AI budget is used up (Settings → AI brain)")
            return
        prompt = str(args.get('prompt') or '')[:MAX_PROMPT]
        image = None
        if args.get('image'):
            path = os.path.realpath(os.path.join(runner.data_dir, str(args['image'])))
            if not path.startswith(os.path.realpath(runner.data_dir) + os.sep):
                reply(error='the picture must be in the plugin\'s own folder')
                return
            try:
                with open(path, 'rb') as f:
                    image = f.read(8_000_000)
            except OSError as e:
                reply(error=f'could not read the picture: {e}')
                return
        self._ai_busy.add(runner.id)

        def work():
            try:
                answer = backend.ask(prompt, PLUGIN_SYSTEM, kind='plugin', image=image)
                result = (answer.text, None)
            except Exception as e:        # noqa: BLE001
                result = (None, getattr(e, 'spoken', None) or str(e))
            self._later(finish, *result)

        def finish(text, error):
            self._ai_busy.discard(runner.id)
            reply(text, error)
        threading.Thread(target=work, daemon=True, name=f'plugin-ai-{runner.id}').start()

    # ------------------------------------------------------------ plugin life
    def plugin_started(self, runner):
        pass

    def plugin_stopping(self, runner, reason):
        if self.input_owner is runner:
            self.stop_control(f'{runner.manifest.name} stopped')
        if self._input_waiting and self._input_waiting[0] is runner:
            self._input_waiting = None
        self._share_waiting = [(r, f) for r, f in self._share_waiting if r is not runner]
        self._ai_busy.discard(runner.id)
