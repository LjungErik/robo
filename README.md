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

You can change: size, walking speed, naps, bubble time, update checks, evil mode
and its delay, dressing up and how often, which characters he may become (hover
a character to see its move), and logging.

Settings are saved in `~/.config/robo/settings.json`. You can also edit that
file by hand: he notices within a couple of seconds and applies it.

Command-line flags (`--scale`, `--evil-after`, `--dress-up-every`, `--no-updates`,
`-v`) still work. They override the saved file for that run only. Pressing Apply
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

- Change how often, or which characters he may become, in **Settings**.
- Right-click → **Dress up** to pick a random character now.
- He doesn't dress up while he's evil, but if you leave him alone while he's dressed up you get
  an evil viking (or pharaoh, or…).
- To add a character: draw its outfit in `robo/render/costumes.py`, add its demand
  icon to `robo/render/icons.py`, and list it in `robo/core/characters.py`.

## Talking 🗣️

**Double-click Robo** (or right-click → **Talk to me**) and he says hello,
then listens. Just talk to him. He answers out loud in a squeaky robot voice,
moves his mouth along, and keeps listening until you say goodbye or go quiet.
A single click while he's chatting hushes him.

Things to try: *"tell me a joke"*, *"what time is it?"*, *"how's my battery?"*,
*"dress up as a pirate"*, *"dance!"*, *"sing a song"*, *"you're so cute"*,
*"take a nap"*, *"goodbye"*.

- While he listens his bubble shows a 🎤, and while he thinks a ⚙️.
- Turn on **Listen for "Hey Robo"** in Settings to start a chat by voice.
  This keeps the microphone open. Otherwise the microphone is only on while he listens.
- Pitch, speed, volume and the robot effect are in **Settings → Voice & talking**.
- Speech recognition is **offline** ([Vosk](https://alphacephei.com/vosk/)): nothing you
  say leaves your computer. `install.sh` sets it up in `~/.local/share/robo`
  (its own Python environment plus a ~70 MB English model).
- His voice is espeak-ng with a little robot filter (`robo/audio.py`).
- If he can't hear you, check that your microphone isn't muted in Settings → Sound.

How it works: `robo/core/talk.py` runs the conversation: listen, think, speak,
listen again. `robo/conversation/rules.py` is his brain for now, a simple
"switch statement" of topics where the first match answers. To teach him a new
answer, add a row to `RULES`. To swap in an LLM later, write a
`robo.conversation.Brain` subclass whose `ask()` answers in the background, and
pass it in `robo/app.py` where `RuleBrain()` is used today.

## Interacting

| Action        | Result                                   |
|---------------|------------------------------------------|
| Left-click    | Pat him (hearts!), dismiss the bubble, end his costume, or hush him |
| Double-click  | Talk to him |
| Drag          | Pick him up; he falls back down when you let go |
| Right-click   | Menu: wave, nap / wake, dress up, talk, settings, show all icons, quit |

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
  conversation/           his brain: Brain interface + RuleBrain (keyword switch)
  events.py               Event, list of KINDS, classify() for notification text
  core/                   the robot itself, pure Python (no GUI or OS calls)
    companion.py          ties everything together; the only thing the platform talks to
    body.py               position and movement: idle / walk / sleep / drag / fall
    face.py               blinking, glancing, timed expressions, hearts
    personality.py        what he decides to do and how he reacts  <- tweak his character here
    evil.py               when to turn evil / good, colour blend, glitch
    characters.py         the dress-up characters: move, demand, walk style
    wardrobe.py           when he dresses up, the poof, signature-move timing
    effects.py            particles (numbers, notes, sparks)
    bubble.py             speech bubble queue, duplicates, pop animation
    talk.py               conversations: listen → think → speak → listen
    pose.py               state -> Pose (what one frame should look like)
    layout.py, geometry.py  window size, bubble position, click areas
  render/                 Cairo drawing (portable)
    scene.py              one full frame; robot.py the robot; icons.py the icons;
                          costumes.py the outfits; effects.py particles and poof;
                          anatomy.py body-part positions; shapes.py colours and helpers
  platform/
    base.py               the contract a port implements
    linux/                GTK window, GLib loop, D-Bus notifications, battery, network,
                          updates, idle monitor, single-instance lock, settings window,
                          voice (espeak-ng) and ears (Vosk helper process)
    headless.py           off-screen fake platform used by the tests
tests/test_robot.py       python3 -m unittest discover -s tests
```

Data flows one way: an **EventSource** emits an `Event`, then the `Companion`
updates `Body`, `Face`, `EvilMode` and `BubbleQueue`, then `build_pose()`
produces a `Pose`, then `render` draws it into the window the **WindowHost**
gives it.

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
| `SpeechOutput` | espeak-ng via ctypes + `robo/audio.py` | SAPI / espeak-ng | `AVSpeechSynthesizer` / espeak-ng |
| `SpeechInput` | Vosk helper process | Vosk works there too | Vosk works there too |

Any piece can also be swapped on Linux. For example, a Qt window instead of
GTK only means writing a new `WindowHost` and returning it from
`LinuxPlatform.create_window()`. `platform/headless.py` is the smallest
complete example to copy from.
