# Robo — desktop robot companion

A little robot that lives at the bottom of your Ubuntu desktop. He blinks,
looks around, walks around from time to time, waves, and naps (zzz).
When something happens on your laptop, a speech bubble pops up with an
icon instead of text.

## Install

```bash
./install.sh
```

This installs any missing packages (`python3-gi-cairo`), adds Robo to
autostart and the app menu, and starts him. To remove him, run `./uninstall.sh`.

Run him by hand with `./robot_companion.py` (`--demo` to see every icon,
`-v` to log what he sees).

## Settings ⚙️

Right-click Robo and choose **Settings…**. Move the sliders and switches, then
press **Apply**: he updates right away (no restart) and hops to say thanks.
**Defaults** fills in the original values; they take effect when you press Apply.
**Close** throws away changes you haven't applied.

You can change: size, walking speed, naps, his **look** (who he is the rest of
the time), bubble time, update checks, evil mode and its delay, dressing up and
how often, which characters he may become (hover a character to see its move),
and logging.

Settings are saved in `~/.config/robo/settings.json`. You can also edit that
file by hand: he notices within a couple of seconds and applies it.

Command-line flags (`--scale`, `--look`, `--agent`, `--evil-after`, `--dress-up-every`,
`--no-updates`, `-v`) still work. They override the saved file for that run only. Pressing Apply
saves whatever is in the window, including values that came from flags.

## Evil mode 😈

If you don't touch the keyboard or mouse for a while (1 minute by default), the screen glitches
and Robo turns evil. He gets red angry eyes, fangs, horns and a dark body.
He sneaks around slowly, rubs his hands together and laughs now and then.
As soon as you touch anything he glitches back, looks startled (sweat drop),
then cheers up again.

- Change the delay, or turn evil mode off, in **Settings**.
- He stays good while a video player keeps the screen awake.
- Idle time comes from GNOME's idle monitor, so it sees input in every app.

## Dressing up 🎭

Every so often (about every 45 seconds by default), even while you work, Robo vanishes
in a puff of smoke and comes back as a character. He wanders around,
does his signature move and keeps making demands in his speech bubble.
**Click him** to snap him out of it. Clicking the bubble only closes the bubble.

| Character | Signature move | Demands |
|---|---|---|
| 𓂀 Pharaoh | walks like an Egyptian | a pyramid (of himself) |
| 🤠 Cowboy | twirls his lasso, gallops when walking | a lucky horseshoe |
| ⚔️ Viking | mighty battle cry | mead |
| 🧮 Accountant | furious calculator typing, numbers fly out | receipts (it keeps unrolling) |
| 🔧 Mechanic | bonks his own head with a wrench, sparks fly | an oil can |
| 🏛️ Roman emperor | plays the lyre | grapes |
| 👨‍🍳 Chef | flips a pancake sky-high and catches it | a cupcake |
| 🧑‍🚀 Astronaut | floats in zero gravity among stars, moon-bounce walk | a rocket |
| 🧙 Wizard | casts a spell, sparkles fly from his wand | a bubbling potion |
| 🏴‍☠️ Pirate | dances a jig with the parrot on his shoulder | treasure |
| 🦸 Superhero | flies up, fist first, cape trailing | a kitten to rescue |
| 🐱 Kitty | bats at a ball of yarn, `:3`, little hearts | a fish |
| 🦾 Iron Man | repulsor blast; **flies around the screen** on boot jets and hovers | shawarma |
| 🕷️ Spider-Man | thwips webs; **zips up to the top of the screen** and hangs there | pizza |
| 🧤 Thanos | snaps his fingers (dust drifts away); **teleports** across the screen | the six stones |
| 🦸 (Superhero) | also takes off and flies somewhere now and then | |

- Change how often, or which characters he may become, in **Settings**.
- Right-click → **Dress up** to pick a random character now.
- He doesn't dress up while he's evil, but if you leave him alone while he's dressed up you get
  an evil viking (or pharaoh, or…).
- To add a character, write a character file (see below). No code needed.

## His look, and getting around 🚀

**Settings → Robo → Look** picks who he is the rest of the time: plain Robo, or any
character (`--look ironman` for one run). Some characters don't just walk:

- **Iron Man** takes off now and then, flies to a random spot anywhere on your
  screen, hovers there, maybe flies on, and lands. Let go of him in mid-air and
  he just hovers.
- **Spider-Man** shoots a web line up to the top of the screen; where it sticks a
  web spins itself out, spokes first and then the spiral, like a real spider's. He
  zips up the line, hangs there swinging with his legs dangling, then lets go and
  drops, or lowers himself back down on the thread.
- **Thanos** snaps his fingers, vanishes in a puff of smoke and reappears
  somewhere else.

Right-click → **Fly around** (or say *"fly around!"*) makes him go now. He always
lands to work on a task, to turn evil, or when he changes into someone who can't fly.

## Your own characters 🎨

What Robo and every character look like, and how they behave, lives in
**character files** (YAML) in `robo/characters/`. The code is only an
interpreter for them, so anyone can design their own version of Robo:

1. Copy a file (`robo/characters/pharaoh.yaml` is a small costume,
   `robo.yaml` is the whole robot) to `~/.config/robo/characters/` and edit it.
   A file with the same `id` as a built-in one replaces it.
2. Robo picks up changes while he runs. New characters appear in Settings.
3. Check it: `python3 -m robo --check ~/.config/robo/characters/mine.yaml` reports
   mistakes and saves a preview picture of every pose next to the file.

A file can recolour the robot, add outfit layers (hats, capes, armour), replace
body parts, add arm gestures, particles, a signature move, the icon he demands,
the words you can use to ask for him, and `travel` abilities (fly, hang, teleport).
Every number can be a small expression like `"sin(t * 3) * 6"` for animation.
The format is described in [`robo/characters/README.md`](robo/characters/README.md).

## Talking 🗣️

**Double-click Robo** (or right-click → **Talk to me**) and he says hello,
then listens. Just talk to him. He answers out loud in a soft, friendly voice,
moves his mouth along, and keeps listening until you say goodbye or go quiet.
**Evil Robo** has a deep, buzzy robot voice instead. You can also hear it by
asking him *"are you evil?"*.
A single click while he's chatting hushes him.

Things to try: *"tell me a joke"*, *"what time is it?"*, *"how's my battery?"*,
*"dress up as a pirate"*, *"turn into iron man"*, *"fly around!"*, *"dance!"*,
*"sing a song"*, *"you're so cute"*,
*"take a nap"*, *"do a task"*, *"abort task"*, *"goodbye"*.

- While he listens his bubble shows a 🎤, and while he thinks a ⚙️.
- Turn on **Listen for "Hey Robo"** in Settings to start a chat by voice.
  This keeps the microphone open. Otherwise the microphone is only on while he listens.
- Pitch, speed and volume are in **Settings → Voice & talking**. Switch on
  **Robotic voice** if you want the beepy voice all the time.
- Speech recognition is **offline** ([Vosk](https://alphacephei.com/vosk/)): nothing you
  say leaves your computer, unless you give him an AI brain (below). `install.sh` sets everything up in `~/.local/share/robo`:
  its own Python environment, a ~70 MB English recognition model and the ~60 MB voice.
- His nice voice is [Piper](https://github.com/OHF-Voice/piper1-gpl) (offline neural
  speech, voice `en_US-hfc_female-medium`, lifted a little in pitch). The evil and robotic
  voices are espeak-ng with a robot filter (`robo/audio.py`).
- If he can't hear you, check that your microphone isn't muted in Settings → Sound.

How it works: `robo/core/talk.py` runs the conversation: listen, think, speak,
listen again. `robo/conversation/rules.py` is his own little brain, a simple
"switch statement" of topics where the first match answers. To teach him a new
answer, add a row to `RULES`.

## AI brain 🧠

Give him an AI agent and he can answer anything you ask, remember what you said
earlier in the chat, and still dress up, dance or fly when the AI thinks it fits.
Pick one in **Settings → AI brain → Talk through** (or `--agent claude` for one run):

| Choice | Uses | Log in once with |
|---|---|---|
| Claude | [Claude Code](https://claude.com/claude-code) (`claude -p`) | `claude`, then `/login` with your Claude Pro / Max account |
| ChatGPT | OpenAI [Codex CLI](https://github.com/openai/codex) (`codex exec`) | `codex login` with your ChatGPT account |
| Gemini | Google [Gemini CLI](https://github.com/google-gemini/gemini-cli) (`gemini -p`) | `gemini`, then "Login with Google" |

- **No API keys.** Robo runs the provider's own app, which keeps its own login, so a
  Claude Pro subscription works exactly as it does in Claude Code. Robo never sees a
  password, key or token, and API-key environment variables are not passed on (so it is
  your subscription that answers, not a pay-per-use key). The settings window shows
  whether the chosen app is installed and logged in, and what to run if it isn't.
- **Chatting has no tools.** For a chat the agent runs with no tools in an empty folder
  of Robo's own (`~/.local/share/robo/agent`): it can't read your files, run commands or
  browse. Real work goes through tasks (above), which are sandboxed.
- **What stays local:** tasks, goodbye, and short commands ("dress up as a pirate",
  "fly around", "what time is it") are answered by his own brain, instantly and offline.
  Longer requests ("dress up as a pirate and tell me a pirate fact") go to the agent.
- **Privacy:** what you say to him (after speech recognition) is sent to the provider you
  picked, along with a short status line (time, battery, his costume).
- Answers take a few seconds (he shows the ⚙️ thinking bubble). Click him to hush him;
  that also cancels the question. After 30 minutes without talking he starts a fresh
  conversation. `agent_model` in `settings.json` picks a model (default: the app's own).
- Claude is tested; the ChatGPT and Gemini connections follow their CLIs' documentation
  but haven't been tried against real installations yet.
- Using your own subscription through your own Claude Code is normal personal use. If you
  ever distribute Robo as a product, check Anthropic's (and OpenAI's / Google's) terms
  about third-party apps using consumer subscription logins.

How it works: `robo/agents/` has one small class per provider (`claude.py`, `codex.py`,
`gemini.py`) that runs its CLI and reads the answer; `robo/conversation/agent.py`
(`AgentBrain`) decides what goes to the agent, runs it on a worker thread, and turns its
JSON answer into a `Reply`. To add a provider, subclass `AgentBackend` and add it to
`BACKENDS` in `robo/agents/__init__.py`.

## Tasks 💻

With **Claude** as his AI brain (Settings → AI brain), Robo does real work for you:
sorting, tidying, summarising, writing, renaming, converting, checking files.

- **Right-click → Give me a task…** opens a form: type what he should do and pick the
  files or folders he may **look at** and the ones he may **change**.
- Or just **tell him**: *"make me a to-do list from the meeting notes in my Documents
  folder"*. Claude works out the task and which folders it needs, and Robo asks you
  to approve exactly that first.
- He changes into his 80s hacker outfit and types away while the agent works.
  *"How's the task going?"* tells you what he's doing; *"abort task"* stops it.
- When he's done he **tells you what he did**, and you **review every change** before
  anything of yours is touched. New files he makes (reports, lists, notes) go to a new
  folder in `~/Robo/`, also after your review.

**How it stays safe.** The agent's brain and its hands are kept apart:

- **Brain:** Claude Code runs outside the sandbox (it needs the internet and your
  login), with **all of its own tools switched off**.
- **Hands:** its only tools are Robo's (read, write, edit, move, list files, run a
  command), served by `robo/sandbox/worker/mcp_server.py` **inside the sandbox** below.
  So whatever it decides, it works on copies, in a folder with no internet, nothing of
  yours but what you granted, and no way to your login or your keys.
- Your home folder itself and hidden folders in it (`~/.ssh`, keyrings, browser
  profiles, app logins) can never be granted.
- **Note:** everything the agent reads is sent to Claude, because that's how it thinks.
  Only grant what you're happy to share.
- ChatGPT (Codex) and Gemini can only chat for now: their own shell / file tools can't
  be fully switched off, so they could read things you didn't give them.
- Without an AI brain, *"do a task"* still runs the old placeholder (1-2 minutes of
  pretend hacking).
- **Interrupt him** any time: double-click to talk, or pick him up. He stops typing and
  helps you; the agent keeps thinking in the background, and he sits back down after.
- Ask for another task while he's busy and it's queued. *"Abort all tasks"* drops them all.
- The hacker outfit is only for work: he doesn't dress up as anything else or turn evil
  while he has a task.

How it works: `robo/tasks/` is pure logic. `Task` (`base.py`) has the lifecycle
(start, pause, resume, abort, done, failed), `TaskManager` (`manager.py`) runs
`max_parallel` tasks at once (1 today), queues the rest, and pauses for each
interruption reason (`'conversation'`, `'held'`). `catalog.py` lists the kinds of
task, `agent_task.py` is the AI agent task. `robo/core/hacker.py` decides how he
looks (outfit, sitting, typing); the outfit is `robo/characters/hacker.yaml`.

To add a hand-written (non-AI) task:
1. Write its job in `robo/sandbox/worker/jobs.py`. This code runs inside the sandbox.
2. Add a factory to `TASK_KINDS` in `robo/tasks/catalog.py` that returns a
   `SandboxedTask` with the `Permissions` it needs (default: none).
3. Add a phrase to `RuleBrain` that replies with
   `action='start_task', action_arg='<kind>'`.

## Sandbox 🔒

Every task runs in a **sandbox**: a separate process that can only reach what you
allowed. Robo himself (window, microphone, chatting) stays outside it.

| The task can't... | because |
|---|---|
| see or delete your files | It only sees its own folder (`~/.local/share/robo/tasks/<id>/work`), plus files you granted. |
| change your files behind your back | Files you let it change are **copies**. When it's done Robo lists what changed and asks before applying anything. Edits to files you changed meanwhile are skipped, and symlinks it makes never leave the sandbox. |
| download anything you didn't allow | It has no network at all. Downloads go through Robo, who checks each one against the hosts you approved (redirects too). |
| become root | It runs as your normal user with no way to gain more rights: no `sudo`, `pkexec` or setuid programs, and no capabilities. |
| touch your desktop | No display, D-Bus, keyring, ssh-agent or environment variables of yours. |
| hog the computer | Memory, process count, one CPU core, file size and running time are all capped. |

- A task that needs anything (reading or changing files, downloading) **asks you
  first** in a dialog. Closing the dialog means no.
- If no sandbox is available, Robo **refuses** to do tasks and tells you why. It never
  falls back to running them unprotected.
- On Linux the sandbox is [bubblewrap](https://github.com/containers/bubblewrap)
  (`sudo apt install bubblewrap`) with `systemd-run --user` for the limits.
- The worker's output goes to `worker.log` next to its `work/` folder. The 20 newest
  workspaces are kept.

How it works: `robo/sandbox/` is portable. `Permissions` says what a task may
touch, `Workspace` makes its folder and stages copies, `Broker` handles requests
from inside, `Approver` asks you, and `worker/` is the stdlib-only code that runs
inside. Each OS supplies a `SandboxBackend` (`robo/sandbox/backend.py` lists the
rules it must follow, with ideas for Windows and macOS) from `Platform.sandbox()`.
`tests/test_sandbox.py` has a `SandboxConformance` suite that checks those rules
from inside a real sandbox. Run it against any new backend.

## Interacting

| Action        | Result                                   |
|---------------|------------------------------------------|
| Left-click    | Pat him (hearts!), dismiss the bubble, end his costume, or hush him |
| Double-click  | Talk to him |
| Drag          | Pick him up; he falls back down when you let go |
| Right-click   | Menu: wave, do / abort a task, nap / wake, dress up, fly around (if he can), talk, settings, show all icons, quit |

## What triggers a bubble

| Icon | When |
|------|------|
| 🪫 battery_low | Battery drops to 20 %, 10 %, 5 % (or GNOME warns) |
| ⚡ battery_charging | Charger plugged in |
| 🔋 battery_full | Battery reaches 100 % while plugged in |
| 📦 update | apt / snap / flatpak updates available (checked every 2 h) |
| 🔄 reboot | A restart is required |
| ✉️ mail · 💬 chat · 📅 calendar · ⏰ alarm | Desktop notifications from those apps |
| 📶 wifi / wifi_off | Internet connection comes back / is lost |
| ⬇️ download · 📷 camera · 🎵 music · 🔵 bluetooth · 💾 usb · ⚠️ warning | Matching notifications |
| 🔔 bell | Any other notification |

Every desktop notification is caught by listening on the session D-Bus
(`org.freedesktop.Notifications` and `org.gtk.Notifications`), then sorted by
its category hint and keywords (see `KEYWORD_RULES` in `watchers.py`). If the
same notification repeats, a number badge appears on the bubble.

Test it with: `notify-send "Battery low" "9% left"` or `notify-send -c email.arrived "New mail"`.

## Notes

- GNOME on Wayland doesn't let apps place their own windows, so Robo runs
  through XWayland (`GDK_BACKEND=x11`). This is set automatically.
- Only the robot and his bubble catch mouse clicks. The rest of his window
  lets clicks through to whatever is underneath.

## Code layout

```
robot_companion.py        launcher (same as `python3 -m robo`)
robo/
  app.py                  RoboApp: command line, wiring, applying settings live
  config.py               Settings + FIELDS (describes every setting for the settings window)
  settings_store.py       settings.json load / save / change detection
  audio.py                voice effects (robot filter, chirps, mouth envelope)
  conversation/           his brain: Brain interface + RuleBrain (keyword switch) +
                          AgentBrain (an AI agent for everything else)
  agents/                 AI agents through their own logged-in CLIs: Claude Code, Codex,
                          Gemini CLI (no API keys)
  tasks/                  work you give him: Task lifecycle, TaskManager (queue, pauses), catalog,
                          SandboxedTask
  sandbox/                portable sandbox parts: Permissions, Workspace + change review,
                          Broker (downloads), Approver; worker/ runs inside the sandbox
  events.py               Event, list of KINDS, classify() for notification text
  characters/             CHARACTER FILES: robo.yaml (the robot), costumes, hacker.yaml;
                          README.md describes the format
  design/                 reads them: expr.py (safe expressions), loader.py (one file),
                          registry.py (all files, user folder, hot reload, Designs),
                          model.py (Character, Move, Travel), check.py (--check)
  core/                   the robot itself, pure Python (no GUI or OS calls)
    companion.py          ties everything together; the only thing the platform talks to
    body.py               position and movement: idle / walk / sleep / drag / fall /
                          fly / hover / hang
    travel.py             getting around without walking: fly, hang, teleport
    face.py               blinking, glancing, timed expressions, hearts
    personality.py        what he decides to do and how he reacts  <- tweak his character here
    evil.py               when to turn evil / good, colour blend, glitch
    characters.py         the characters from the files: costumes, looks, demands
    wardrobe.py           when he dresses up, the poof, signature-move timing
    hacker.py             hacker mode while he has a task: outfit on/off, sitting, typing
    effects.py            particles (numbers, notes, sparks)
    bubble.py             speech bubble queue, duplicates, pop animation
    talk.py               conversations: listen → think → speak → listen
    pose.py               state -> Pose (what one frame should look like)
    layout.py, geometry.py  window size, bubble position, click areas
  render/                 Cairo drawing (portable)
    scene.py              one full frame; robot.py the rig (draws a Design's parts and
                          layers); interpreter.py turns file drawings into Cairo calls;
                          icons.py the icons; effects.py particles and poof;
                          shapes.py colours and helpers
  platform/
    base.py               the contract a port implements
    linux/                GTK window, GLib loop, D-Bus notifications, battery, network,
                          updates, idle monitor, single-instance lock, settings window,
                          voice (espeak-ng) and ears (Vosk helper process),
                          task sandbox (bubblewrap) and permission dialogs
    headless.py           off-screen fake platform used by the tests
tests/test_robot.py       python3 -m unittest discover -s tests
tests/test_characters.py  character files, user characters, flying / hanging / teleporting
tests/test_agent.py       the AI brain, with fake Claude / Codex / Gemini CLIs
tests/test_agent_tasks.py agent tasks: the sandboxed MCP tools, a fake agent, the escape test
tests/test_sandbox.py     sandbox rules, checked inside a real sandbox
```

Data flows one way: an **EventSource** emits an `Event`, then the `Companion`
updates `Body`, `Face`, `EvilMode` and `BubbleQueue`, then `build_pose()`
produces a `Pose`, then `render` draws it into the window the **WindowHost**
gives it, using the `Design` the character files describe for his look and outfit.

## Porting to another OS

The core and the renderer only need Python and pycairo. A port writes a
new `robo/platform/<os>/` package that implements the classes in
`robo/platform/base.py`, then adds it to `load_platform()` in
`robo/platform/__init__.py`:

| Piece | Linux (today) | Windows idea | macOS idea |
|---|---|---|---|
| `Scheduler` | GLib main loop | Qt / Tk event loop | NSRunLoop (PyObjC) |
| `WindowHost` | GTK popup + input shape | layered window (`WS_EX_LAYERED`, `WS_EX_TRANSPARENT`) | borderless `NSWindow`, `ignoresMouseEvents` |
| notifications `EventSource` | D-Bus monitor | WinRT `UserNotificationListener` | not readable by apps, use the other sources |
| battery / network | sysfs, NetworkManager | `psutil`, `GetSystemPowerStatus` | `psutil`, `SystemConfiguration` |
| updates | apt / snap / flatpak | `winget upgrade` | `softwareupdate -l`, `brew outdated` |
| `IdleMonitor` | Mutter idle monitor | `GetLastInputInfo` | `CGEventSourceSecondsSinceLastEventType` |
| settings window (optional) | GTK 3, built from `config.FIELDS` | Qt / Tk form from the same `FIELDS` | same |
| `SpeechOutput` | Piper (nice) + espeak-ng (evil), `robo/audio.py` | Piper works there too | Piper works there too |
| `SpeechInput` | Vosk helper process | Vosk works there too | Vosk works there too |
| `SandboxBackend` | bubblewrap + `systemd-run --user` | AppContainer + Job Object | `sandbox-exec` profile + `setrlimit` |
| `Approver` | GTK dialogs | Qt / WinUI dialog | `NSAlert` |

Any piece can also be swapped on Linux. For example, a Qt window instead of
GTK only means writing a new `WindowHost` and returning it from
`LinuxPlatform.create_window()`. `platform/headless.py` is the smallest
complete example to copy from.
