"""All plugins: finding them, switching them on and off, hot reloading.

Plugin folders are read from robo/plugins/builtin/ (examples that come with
Robo) and ~/.config/robo/plugins/ (yours). Each has a plugin.json and its
code. Every second the manager looks at the files: a new folder shows up
(switched off until you turn it on), an edited one is reloaded (its process
restarted with the new code), a deleted one stops. Robo himself keeps running.

What you switched on, and the permissions you granted, are kept in
~/.local/share/robo/plugins.json. If a plugin later asks for more
permissions than you granted, it stays off until you look at it again.
"""
import json
import logging
import os
import re

from .manifest import ManifestError, load_manifest, signature
from .runner import BROKEN, PluginRunner

log = logging.getLogger(__name__)

BUILTIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'builtin')
SCAN_SECONDS = 1.0


def _plain(text):
    return ' '.join(re.sub(r"[^a-z0-9' ]+", ' ', str(text or '').lower()).split())


class PluginManager:
    def __init__(self, backend, data_dir, services, clock, directories=(BUILTIN_DIR,),
                 state_file=None):
        self.backend = backend             # SandboxBackend (None: plugins can't run here)
        self.data_dir = data_dir           # each plugin's own folder goes in here
        self.services = services
        self.clock = clock
        self.directories = list(directories)
        self.state_file = state_file
        self.runners = {}                  # id -> PluginRunner
        self.problems = {}                 # folder -> why it couldn't be loaded
        self.choices = {}                  # id -> {'enabled': bool, 'granted': [...]}
        self.on_new_plugin = None          # (manifest) -> None, for "I found a plugin"
        self._signatures = {}              # id -> files signature
        self._next_scan = 0.0
        self._load_choices()

    # ------------------------------------------------------------ remembering
    def _load_choices(self):
        try:
            with open(self.state_file, encoding='utf-8') as f:
                data = json.load(f)
            self.choices = {k: v for k, v in data.items() if isinstance(v, dict)}
        except (OSError, TypeError, ValueError):
            self.choices = {}

    def _save_choices(self):
        if not self.state_file:
            return
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            tmp = self.state_file + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.choices, f, indent=2)
            os.replace(tmp, self.state_file)
        except OSError as e:
            log.warning('could not save plugin choices: %s', e)

    def granted(self, pid):
        return set((self.choices.get(pid) or {}).get('granted') or ())

    def enabled(self, pid):
        """Switched on, with every permission it asks for granted."""
        runner = self.runners.get(pid)
        choice = self.choices.get(pid) or {}
        return bool(choice.get('enabled') and runner and
                    set(runner.manifest.permissions) <= set(choice.get('granted') or ()))

    def needs_review(self, pid):
        """On, but it now asks for permissions you never granted."""
        runner = self.runners.get(pid)
        return bool((self.choices.get(pid) or {}).get('enabled') and runner
                    and not self.enabled(pid))

    def set_enabled(self, pid, on):
        """Switch a plugin on (granting what it asks for) or off."""
        runner = self.runners.get(pid)
        if runner is None:
            return
        self.choices[pid] = {'enabled': bool(on),
                             'granted': list(runner.manifest.permissions) if on else []}
        self._save_choices()
        if on:
            runner.crashes = 0
            runner.start()
        else:
            runner.stop()

    # ------------------------------------------------------------ finding them
    def scan(self):
        found = {}
        problems = {}
        for d in self.directories:
            try:
                names = sorted(os.listdir(d))
            except OSError:
                continue
            for n in names:
                folder = os.path.join(d, n)
                if n.startswith(('.', '_')) or not os.path.isdir(folder):
                    continue
                try:
                    m = load_manifest(folder)
                except ManifestError as e:
                    problems[folder] = str(e)
                    continue
                found[m.id] = m                # a later folder replaces an earlier one
        self.problems = problems
        for pid in list(self.runners):
            if pid not in found:
                log.info('plugin %s was removed', pid)
                self.runners.pop(pid).kill('removed')
                self._signatures.pop(pid, None)
        for pid, m in found.items():
            sig = signature(m.folder)
            runner = self.runners.get(pid)
            if runner is None:
                runner = self.runners[pid] = PluginRunner(
                    m, self.backend, os.path.join(self.data_dir, pid), self.services,
                    self.clock)
                self._signatures[pid] = sig
                if pid not in self.choices and self.on_new_plugin:
                    self.on_new_plugin(m)
                if self.enabled(pid):
                    runner.start()
            elif sig != self._signatures.get(pid):
                self._signatures[pid] = sig
                runner.manifest = m
                log.info('plugin %s changed: reloading', pid)
                if self.enabled(pid):
                    runner.reload()
                else:
                    runner.kill('changed')
                    if runner.state == BROKEN:
                        runner.state = 'off'

    def update(self, now):
        if self.backend is not None and now >= self._next_scan:
            self._next_scan = now + SCAN_SECONDS
            self.scan()
        for runner in list(self.runners.values()):
            runner.update(now)
        self.services.update(now)

    def reload(self, pid):
        runner = self.runners.get(pid)
        if runner is not None and self.enabled(pid):
            runner.reload()

    def shutdown(self):
        self.services.stop_control('Robo is closing')
        for runner in self.runners.values():
            runner.kill('Robo is closing')

    # ------------------------------------------------------------ using them
    def running(self):
        return [r for r in self.runners.values() if r.running]

    def command_for(self, heard):
        """(runner, command id) for something you said, or None. A phrase counts
        when what you said starts with it or is it ("play with me minecraft")."""
        text = _plain(heard)
        best = None
        for r in self.running():
            for c in r.commands:
                for phrase in c.get('phrases') or ():
                    p = _plain(phrase)
                    if p and (text == p or text.startswith(p + ' ')
                              or re.search(r'\b' + re.escape(p) + r'\b', text)):
                        if best is None or len(p) > best[2]:
                            best = (r, c.get('id'), len(p))
        return best[:2] if best else None

    def tools(self):
        """[(plugin, tool dict)] his AI brain may use."""
        return [(r, t) for r in self.running() for t in r.tools]

    def find_tool(self, name):
        for r, t in self.tools():
            if t.get('name') == name:
                return r
        return None

    def describe_tools(self):
        """One line per tool, for the AI brain's prompt."""
        lines = []
        for r, t in self.tools():
            params = t.get('params') or {}
            args = ', '.join(f'{k}: {v}' for k, v in params.items())
            lines.append(f'{t["name"]} ({r.manifest.name}): {t.get("description", "")}'
                         + (f'; args {{{args}}}' if args else ''))
        return lines

    def menu_items(self):
        """[(label, runner, menu id)]"""
        return [(m.get('label', '?'), r, m.get('id')) for r in self.running()
                for m in r.menus]
