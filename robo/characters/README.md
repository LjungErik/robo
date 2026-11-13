# Character files

Everything Robo looks like, and every character he can become, is a file in
this folder. The code only *interprets* these files, so you can design your own
Robo, or a new character, without touching any Python.

- **Your own files** go in `~/.config/robo/characters/`. A file there with the
  same `id` as a built-in one replaces it, so you can even redesign Robo himself.
- **Edits show up live.** Robo re-reads the files every couple of seconds while he runs.
- **Check your file** (and get a preview picture of every pose) with
  `python3 -m robo --check ~/.config/robo/characters/mine.yaml`.
  Run `python3 -m robo --check` with no file to check all of them.
- Files are YAML (`.yaml`) or JSON (`.json`). A broken file is skipped with a
  warning; a broken drawing is skipped while Robo keeps running.

The quickest start: copy `pharaoh.yaml` (a small costume) or `robo.yaml`
(the whole robot) and change things.

## The three kinds of file (`role:`)

| role | what it is | examples |
|---|---|---|
| `base` | A whole robot: every body part. Pick it under **Settings → Robo → Look**. | `robo.yaml` |
| `costume` (default) | An outfit drawn on top of a base, plus how the character behaves. He dresses up as these, and you can also pick one as his everyday **Look**. | `pirate.yaml`, `ironman.yaml` |
| `work` | An outfit worn for a reason, never picked at random. | `hacker.yaml` (while he does a task) |

## Coordinates

`(0, 0)` is the ground between his feet. **y grows downward**, so he lives at
negative y (the head top is at -112). **+x is the way he faces**; Robo mirrors
everything when he turns around. In `robo.yaml`:

```
 y=-132  antenna ball           (antenna_y = -112: where the antenna sticks out)
 y=-112  top of the head        head is x -37..37, face screen x -28..28, y -104..-64
 y=-87   eyes at x = ±12        mouth at y = -75
 y=-53   top of the body        body x -22..22, down to y = -18
 y=-45   shoulders at x = ±21   arms are 19 long (hand centre)
 y=0     ground                 feet at x = -9 and 13 (y = -5)
```

## Top-level keys

```yaml
id: duck                 # defaults to the file name
name: Duck               # shown in Settings
role: costume            # base | costume | work
order: 300               # position in the Settings lists (smaller = earlier)
words: [duck, ducky]     # "dress up as a ducky" (speech recognition hears plain words)
wear: [summer, music]    # when he likes to wear it (see "Picking what to wear")

move:                    # signature move, done now and then while dressed up
  gesture: flap          # arm gesture (see gestures)
  mood: happy            # face: normal happy surprised sleep sad focus sing cat roar wince ...
  seconds: 3
  particles: feathers    # optional: what flies out (see particles)
  lift: "16 + sin(t * 2) * 6"   # optional: leave the ground during the move
  tilt: 0.2              # optional: lean the head

walk: {speed: 1.2, gallop: true}   # or lift: "abs(sin(phase * 0.6)) * 7"

travel:                  # optional: ways to get around the screen besides walking
  - {kind: fly, chance: 0.3, speed: 190, gesture: fly, hover_gesture: hover,
     tilt: 0.22, stay: [3, 8], hops: [1, 2], height: 20}

demand:                  # what he keeps asking for in his speech bubble
  icon: bread            # a new bubble icon id
  color: orange          # the antenna glows this colour while it shows
  draw: [...]            # a drawing in a 48 x 48 box (variable: t)

palette: {beak: "#FFA94D"}          # colours this file's drawings use
recolor: {body: "#FFE066"}          # change the base design's colours (see below)
layers: {face: [...], head: [...]}  # the outfit (see layers)
parts: {hand: [...]}                # replace whole body parts of the base design
antenna_y: -130                     # move the antenna up to the top of your hat
gestures: {flap: {...}}             # arm poses
particles: {feathers: {...}}        # flying bits
hobbies: {knit: {gesture: knit, mood: focus, seconds: 8}}   # pastimes (see below)
personality: {...}                  # who he is (see below)
```

## Travel: flying, hanging, teleporting

Every time he decides what to do next, each `travel` entry gets a `chance`
to happen instead.

| kind | what happens | keys |
|---|---|---|
| `fly` | takes off, flies to a random spot **anywhere on the screen**, hovers for `stay` seconds, flies on (`hops` spots in total), then lands. If you let go of him in the air, he hovers there. | `speed`, `gesture` (while flying), `hover_gesture`, `tilt`, `stay`, `hops`, `height` (extra lift, for jet flames), `particles` |
| `hang` | **shoots a web line** up to the top of the screen, the web sticks (and your `anchor` layer can spin a web there), **zips up** it, **hangs and swings** for `stay` seconds (legs dangling), then **lets go and drops** or **lowers himself down** on the thread. | `gesture` (while shooting and zipping), `shoot` (s for the line to fly up), `pause` (s before zipping), `speed` (zip), `rope` (how far below the web his hand hangs), `hover_gesture` (hanging), `swing` (radians), `stay`, `end` (`drop`, `lower` or `either`), `climb_gesture`, `lower_speed`, `anchor_dx` (how far in front of his centre the line goes up) |
| `teleport` | does `gesture` for `windup` seconds, vanishes in a puff of smoke and reappears somewhere else. | `gesture`, `windup`, `mood` |

He always comes down to work on a task, to turn evil, or when he changes into
something that can't travel that way. Right-click → **Fly around** (or "fly
around!" out loud) asks him to go now.

Drawings can react: the variables `airborne`, `travel` (`'fly'`, `'hang'`,
`'teleport'` or `''`), `flying`, `hanging` and `cruising` (moving through the
air right now) say what he's doing. See the jet flames in `ironman.yaml`.

**The web (or any line to the top of the screen).** While a `hang` trip is on,
his window becomes a tall column from the top of the screen down to him, and
two layers draw the line. They are *not* mirrored when he turns around, and
he swings around the anchor:

| layer | draws | variables |
|---|---|---|
| `tether` | the line from his hand to the anchor | `hand_x`, `hand_y` (his front hand), `anchor_x`, `anchor_y`, `web` (0..1: how far the line has flown; draw it to `lerp(hand_x, anchor_x, web)`), `web_gone` (seconds since he let go, -1 while holding) |
| `anchor` | whatever is where it sticks, at the top edge of the screen | the same, plus `web_hit` (seconds since it stuck, -1 before) for building it up |

`spiderman.yaml` spins a real orb web at the anchor: the spokes grow first,
then the capture spiral is laid from the hub outward, each strand sagging
toward the hub. A grappling hook, a vine or a bungee cord work the same way.

## Layers (outfits) and parts (the robot)

A base design draws these **parts**, in this order; any other file can replace
one with `parts:`:

| part | what | extra variables |
|---|---|---|
| `shadow` | on the ground, not lifted | |
| `legs` | both legs and feet | `leg_a`, `leg_b` (step heights), `drop` (sinks when sitting) |
| `arm`, `hand` | drawn once per arm, rotated at the shoulder; the hand is at (0, 19) | `side` (-1 back arm, 1 front arm), `angle` |
| `torso` | the body | |
| `head_back` | ears, horns | |
| `head` | head and face screen | |
| `face` | eyes, mouth, cheeks, glitch | |
| `overlay` | sweat drop, on top of hats | |
| `antenna` | drawn at `antenna_y` | |

A costume adds **layers** in between:

| layer | painted | for |
|---|---|---|
| `anchor`, `tether` | before everything (see Travel) | a web line to the top of the screen |
| `behind` | behind everything, even the legs | capes, tails, jet flames |
| `body` | on the torso | collars, ties, armour |
| `behind_head` | behind the head | headdress flaps |
| `face` | on the face | glasses, beards, masks |
| `head` | on the head | hats, helmets |
| `front_hand`, `back_hand` | at the hand, moving with the arm (`rotate: -angle` stands a prop upright) | wands, shields |
| `front` | in front of everything | toys |
| `ground` | on the floor, not bobbing | the hacker's laptop |

## Drawings

A drawing is a list of shapes. Each shape has **one** shape key:

```yaml
- {rect: [x, y, w, h], r: 4}          # r = rounded corners
- {circle: [cx, cy, r]}
- {ellipse: [cx, cy, rx, ry]}
- {arc: [cx, cy, r, from, to]}        # radians, clockwise (negative: true = the other way)
- {poly: [[x, y], [x, y], ...]}       # closed polygon
- {line: [[x, y], [x, y], ...]}       # open line
- {path: "M x y L x y C x1 y1 x2 y2 x y A cx cy r from to Z"}
- {star: [cx, cy, r], points: 5, inner: 0.45}
- {sparkle: [x, y, r]}   {heart: [x, y, size]}
- {text: "$", at: [x, y], size: 10, font: Sans, bold: true, center: true}
- {group: [...]}         # children share transforms, clip and alpha
- {compound: [...]}      # children become one path (even_odd: true cuts holes)
- {choose: [...]}        # draws the first child whose `if` is true
```

Path commands: `M` move, `L` line, `C` curve, `A` arc (`cx cy r from to`),
`N` arc the other way, `S` start a new piece, `Z` close. Arguments are numbers,
expressions without spaces (`-34+trail*0.5`) or `{any expression}`.

**Painting:** `fill: colour`, `stroke: colour` (default: dark ink outline;
`stroke: none` for none), `lw: 2.6` line width, `rope: [colour, inner, outer]`
(thick ink line with a coloured line on top). Fills can also be
`{stripes: [base, stripe], step: 4.5}`,
`{linear: [x0, y0, x1, y1], stops: [[0, colour], [1, colour]]}` or
`{radial: [cx, cy, r0, r1], stops: [...]}`.

**Colours:** `"#RRGGBB"`, `"#RRGGBBAA"`, a palette name, `[colour, alpha]`,
`{mix: [a, b], k: 0.5}`, `{pick: [a, b, c], i: expression}` or `none`.
Built-in names: `ink white black red green yellow blue orange pink purple grey
sky cream`. The base design's palette (`body shade accent screen eye ...`) can
be used and recoloured by any file; `antenna` is the colour of what he is
reporting right now.

**Evil:** a palette colour written `{good: "#...", evil: "#..."}` fades to the
evil one when he turns evil. `recolor` keeps the base's evil colour unless you
give one.

**Control:** `if: condition`, `vars: {name: expression}`, `for: {name: [values]}`,
`repeat: n` (sets `i`), `translate: [x, y]`, `rotate: angle`, `scale: s` or
`[sx, sy]`, and on groups `clip: shape` and `alpha: 0..1`. On a group the
transforms also scale line widths; on any other shape they only move it.

## Expressions

Any number can be a string expression: `"sin(t * 3) * 6"`,
`"1 if mood == 'happy' else 0"`, `"arms in ('fly', 'hover')"`.
Quote them when they contain commas or colons.

- **Functions:** `sin cos tan atan2 sqrt abs min max floor ceil round int
  sign pow clamp smooth lerp pick(i, a, b, ...) hypot rand(a, b) choice(a, b, ...)`
- **Constants:** `pi tau`
- **Variables:** `t` (seconds), `phase` (walk cycle), `walking`, `dangling`,
  `lift`, `squash`, `mood`, `openness` (eyelids), `look` (eye offset), `arms`
  (gesture name), `antenna` (`normal alert sleep evil hack`), `glow`, `tilt`,
  `evil` (0..1), `glitch`, `sweat`, `talk` (mouth, 0..1), `sit` (0..1),
  `facing` (1 or -1), `costume`, `skin` (his look), `airborne`, `travel`,
  `flying`, `hanging`, `cruising`, `bob`, `leg_a`, `leg_b`, `drop`,
  `head_top`, `antenna_y`
- Only this small, safe subset of Python works: no attributes, indexing,
  imports or anything else, so a character file can't run code.

## Gestures

```yaml
gestures:
  flap: {back: "1.4 + sin(t * 20) * 0.4", front: "-1.4 - sin(t * 20) * 0.4",
         place: behind, head_x: 0}
```

Angles in radians: 0 = arm hanging down, a positive `back` swings the back arm
out, a negative `front` lifts the front arm. `place`: `behind` (default),
`front` (both hands in front of the body) or `over_head` (front arm in front of
the head). `head_x` slides the head sideways. `robo.yaml` has `rest swing wave
up scheme fly hover`; any file's gestures can be used by every character.

## Personality and pastimes

```yaml
personality:
  traits: [curious, warm, a little cheeky]
  speech: "Short, warm sentences. Says beep and boop."   # how he talks
  likes: [pats, music]
  dislikes: [being ignored]
  quirks: [hums when he's happy]
  lines:                       # what he says on his own when there's no AI brain
    morning: ["Good morning{, name}!"]
    welcome_back: ["Welcome back{, name}! You were gone {minutes} minutes."]
```

The AI brain gets all of it with every message, so it stays in character. A costume's
personality replaces Robo's piece by piece: give only `speech` and a few `lines` and
the rest stays Robo's. Line kinds: `first_meeting`, `morning`, `welcome_back`,
`break`, `late`, `bored`, `remark`, `question`, `sleepy`, `picked_up_happy`,
`picked_up_grumpy`, `put_down`, `task_started`, `hobby`. `{, name}` becomes
", Erik" once he knows your name (or nothing yet), `{name}` just the name;
`welcome_back` and `break` can use `{minutes}`, `late` `{time}`.

`hobbies:` are pastimes he picks when nothing is going on (more often when he's
bored): each is a move (`gesture`, `mood`, `seconds`, optional `particles`). While he
does one, drawings can check the variable `hobby` (`robo.yaml` draws a book for
`hobby == 'read'` and juggling balls for `'juggle'`). Eyes can use `look_y` (he looks
up / down at your mouse pointer) as well as `look`.

## Picking what to wear

Robo chooses his outfits himself. When it's time to dress up, every costume
ticked in Settings gets a score and he picks one by weighted chance:

- **The situation.** `wear:` lists the moments the outfit suits; each one that's
  true right now makes it more likely (two at most count).
- **His taste.** Every outfit starts with a small built-in liking, so he has
  favourites from day one. Chatting with him or complimenting him while he wears
  it, or asking for it by name, makes him like it more. Clicking him out of it
  within 20 seconds makes him like it less. His taste is kept in
  `~/.local/share/robo/outfits.json`.

When he picked it for a reason he sometimes says why (more often the chattier he
is, never in quiet hours): the `dressed_up` line, with `{outfit}` and `{because}`
("it's winter"). "Wear whatever you like" lets him pick while you chat.

| situation | true when |
|---|---|
| `morning` `lunch` `afternoon` `evening` `night` | 5-11, 11-14, 14-18, 18-22, 22-5 |
| `monday` `friday` `weekend` | the day of the week |
| `spring` `summer` `autumn` `winter` | the season (northern hemisphere) |
| `halloween` `christmas` `new_year` `valentine` | Oct 20 - Nov 1, Dec 1-26, Dec 31 - Jan 1, Feb 14 |
| `happy` `sad` `bored` `tired` | how he feels |
| `music` `mail` `chat` `meeting` `fixing` | a notification like that in the last 15 minutes (`fixing`: updates / restart) |
| `working` | you've been at the computer for an hour without a break |
| `back` | you came back from a break in the last 15 minutes |
| `video` | a video or presentation is keeping the screen awake |

## His own designs

With the Claude AI brain he can design new outfits himself: ask him ("design
yourself a disco knight outfit", or just "design a new outfit"), or switch on
**Settings → Characters → Design new outfits on his own** (at most once a day
to every two weeks, using your Claude account).

He works on it at his laptop for a few minutes. Claude gets only a design kit:
this README, a few example files, the list of outfits that already exist, and
the checker. None of your files, and no internet. It writes the file, runs the
checker, looks at the preview picture and improves it. Robo then checks the file
again himself, and only one that loads and draws without a single problem is
kept. It goes to `~/.config/robo/characters/robo-made/` and he puts it on right
away. Edit those files like any other, or remove one in Settings (it goes to
the trash).

## Particles

```yaml
particles:
  feathers:
    rate: 6                  # per second
    life: 1.2                # seconds
    vars: {side: "choice(-1, 1)"}
    at: ["f * 20", -50]      # f = the way he faces (1 or -1)
    velocity: ["f * rand(10, 30)", "rand(-30, -10)"]
    glyph: spark             # note spark star magic heart text, or:
    draw:                    # your own drawing (variables x, y, k = age 0..1, i)
      - {ellipse: [x, y, 3, 1.5], fill: [white, "1 - k"]}
```

For `glyph: text`, `text: "01"` picks a random character and `colors:` cycles
through colours.
