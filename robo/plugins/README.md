# Making a Robo plugin 🧩

A plugin gives Robo a new ability (a game, a tool, a gadget) **while he runs**.
Save a file and he reloads that plugin within a second. No restart, no build.

## The smallest plugin

Make a folder in `~/.config/robo/plugins/`, for example `hello/`, with two files:

`plugin.json`
```json
{
  "id": "hello",
  "name": "Hello",
  "description": "Says hello back.",
  "version": "1.0",
  "icon": "👋",
  "permissions": []
}
```

`plugin.py`
```python
from robo_plugin import plugin

@plugin.command('say hello', 'hello plugin')
def hello(text):
    plugin.emote('wave')
    return 'Hello from my very first plugin!'
```

Robo notices the new folder and tells you. Switch it on in **Settings → Plugins**,
then double-click Robo and say *"say hello"*. Change the text, save, and ask again:
the new version answers. `robo/plugins/builtin/dice` is a slightly bigger example.

## What a plugin can do

| | |
|---|---|
| `@plugin.command('phrase', ...)` | You say (part of) a phrase; the handler gets what you said and returns what Robo says. |
| `@plugin.tool('name', 'what it does', arg='meaning')` | His AI brain may use it while chatting ("roll a 20-sided dice for me"). Returns a short result that Robo says. |
| `@plugin.menu('🎲  Label')` | An item in his right-click menu. |
| `@plugin.background` | Runs on its own thread while the plugin is on. Loop with `while plugin.wait(seconds):`. |
| `@plugin.on('start' / 'stop' / 'input_stopped')` | Started, being stopped (reload or switched off), you took the controls back. |
| `plugin.say(text, mood)` | Robo says it out loud. |
| `plugin.emote('wave' / 'cheer' / 'hearts' / 'laugh' / 'dance')` | |
| `plugin.log(...)` / `print(...)` | Goes to its log (Settings → Plugins → Log). |

These need a **permission** (in `plugin.json`, granted when you switch it on):

| permission | |
|---|---|
| `screen` | `plugin.screen.ask()` asks you to share your screen or a window (GNOME's picker); `plugin.screen.grab()` gives a PNG of it (a path in the plugin's folder). |
| `camera` | `plugin.camera.snapshot()` takes one picture (PNG path). Robo looks up while it does, and the camera light comes on. |
| `input` | `plugin.input.start(why)` asks to use your keyboard and mouse (GNOME's own dialog, every time). Then `press('ctrl+s')`, `hold('w', 1.5)`, `down/up(key)`, `type('text')`, `move(dx, dy)`, `click('left', hold)`, `scroll(steps)`, `release_all()`, `stop()`. |
| `ai` | `plugin.ai.ask(prompt, image=path)` asks his AI brain (the one picked in Settings), returns its text. It uses your plan, like chatting does. |

Requests Robo refuses raise `robo_plugin.RoboError` with the reason.

## Keyboard and mouse: you are always in charge

When a plugin has the controls, GNOME shows its indicator and Robo shows an
orange banner, "Robo is using your keyboard and mouse  [Stop]". Any of these
gives the controls back **at once**, with every key let go:

- saying **"stop"** (or "mute", "that's enough"). The microphone listens for
  just these while a plugin has the controls, and for "Hey Robo";
- clicking Robo, his menu (*Take back my keyboard and mouse*), the banner's Stop,
  or GNOME's indicator;
- the plugin stopping, crashing or being reloaded.

Only one plugin at a time can have the controls. Keys are names: `w`, `space`,
`Return`, `Escape`, `Tab`, `ctrl`, `shift`, `alt`, `super`, `Up`, `F5`; combos join
with `+`. Mouse movement is relative (what games use to look around).

## Where it runs

Each plugin is its own process in the same sandbox as Robo's tasks
(bubblewrap): it sees its own folder as `/work` (keep files there) with its
code at `/work/plugin` (read-only), the system's Python and libraries, and
nothing else: **not your home folder, not the network, not your desktop**.
Everything above goes through Robo, who checks the permissions. If a plugin
asks for more permissions in a new version, it stays off until you switch it
on again. A plugin that crashes is restarted (after 1, 3, 10 seconds); one that
keeps crashing waits until you change its files.

Plugin code is plain Python 3 with the standard library (and whatever Python
packages your system has installed). Each handler runs on its own thread, so
it may block; long work belongs in a `@plugin.background` loop or a thread.

## Files

```
robo/plugins/                     Robo's side
  manifest.py   plugin.json, PERMISSIONS
  runner.py     one plugin's process: start, reload, crash, stop
  services.py   every request a plugin makes, behind its permissions
  manager.py    all plugins: folders, on/off, hot reload, commands, tools, menu
  builtin/      dice, camera_peek, game_buddy (off until you switch them on)
robo/sandbox/worker/
  robo_plugin.py   what a plugin imports
  plugin_host.py   runs a plugin inside the sandbox
~/.config/robo/plugins/           your plugins
~/.local/share/robo/plugins/<id>/ each plugin's own folder (/work) and plugin.log
~/.local/share/robo/plugins.json  which ones are on, and what you allowed
```

The messages between Robo and a plugin are described at the top of
`plugin_host.py`.
