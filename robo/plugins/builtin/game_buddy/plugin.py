"""Game buddy: Robo plays along. It combines three of Robo's tools:

    see    the game window you share (plugin.screen)
    think  his AI brain picks a few moves from a picture (plugin.ai)
    act    keys and mouse, after you allow it (plugin.input)

    "play minecraft with me"        he takes every control
    "you do the walking"            just the walking (look / mining stay yours)
    "go chop that tree"             a new goal while playing
    "stop" / click Robo / banner    you have the controls back at once

Each round: look -> think (a few seconds) -> do up to MAX_MOVES moves. Slow
games suit him; he can't react in a split second.
"""
import json
import re
import threading
import time

from games import GROUPS, SAFE_KEYS, find_game, groups_in

from robo_plugin import RoboError, plugin

MAX_MOVES = 6
MAX_SECONDS = 4.0
TALK_EVERY = 25.0           # seconds between things he says while playing
NAMES = {'move': 'the walking', 'look': 'looking around', 'act': 'the actions'}

PROMPT = """You are Robo, playing {game} together with the user. You control: {controls}.
The user controls everything else. The picture is the game right now.
About the game: {about}
Your goal: {goal}
What you did last: {history}

Pick the next few moves (at most {max_moves}) to get closer to the goal. Moves you can use:
{moves}
Answer with ONE JSON object and nothing else:
{{"see": "what you see, a few words", "moves": [ ...moves... ], "say": "optional: something \
short and fun to say to the user, or empty", "done": false}}
Set "done": true only when the goal is reached."""


class Session:
    def __init__(self, game, groups, goal):
        self.game, self.groups, self.goal = game, groups, goal
        self.on = True
        self.history = []
        self.lock = threading.Lock()


current = None


def _controls(groups):
    return ', '.join(NAMES[g] for g in GROUPS if g in groups)


def _say_controls(s):
    return 'everything' if s.groups == set(GROUPS) else _controls(s.groups)


@plugin.command('play with me', "let's play", 'lets play', 'play minecraft', 'play a game',
                'take over', 'you play', 'help me play', 'you do the', 'you take the',
                'you handle the', 'you control the')
def play(text):
    global current
    game, groups = find_game(text), groups_in(text)
    goal = _goal(text) or 'help the user: explore, gather useful things and stay safe'
    if current is not None and current.on:
        with current.lock:
            current.groups, current.game = groups, game
            if _goal(text):
                current.goal = goal
        return f"Okay! Now I'll do {_say_controls(current)}."
    current = Session(game, groups, goal)
    threading.Thread(target=_run, args=(current,), daemon=True).start()
    return (f"Yay, let's play {game.name}! Show me the game window, and let me use the "
            'keyboard and mouse. Say stop whenever you want the controls back.')


@plugin.command('go and', 'go chop', 'go mine', 'go find', 'go get', 'go build', 'new goal',
                'try to')
def new_goal(text):
    if current is None or not current.on:
        return 'Tell me to play with you first!'
    with current.lock:
        current.goal = text
    return 'On it!'


@plugin.command('stop playing', "i'll play", 'i will play', 'my turn', 'give me the controls')
def stop_playing(text):
    if current is None or not current.on:
        return "We aren't playing right now."
    current.on = False
    try:
        plugin.input.stop()
    except RoboError:
        pass
    return 'Okay, the controls are yours! That was fun.'


@plugin.tool('play_game', 'Play a game on screen with the user (they share the game window)',
             what='what they said, e.g. "play minecraft with me, you do the walking"')
def play_tool(what='play with me'):
    return play(what)


@plugin.on('input_stopped')
def given_back(reason=''):
    if current is not None and current.on:
        current.on = False
        plugin.say('Okay, you have the controls! Good game.')


def _goal(text):
    m = re.search(r'\b(?:go and|go|try to|goal is to|help me|let\'s)\s+(.+)', text)
    if m and not re.match(r'(play|take over)\b', m.group(1)):
        return m.group(1)
    return ''


# ---------------------------------------------------------------- playing
def _run(s):
    try:
        if not plugin.screen.shared and not plugin.screen.ask():
            plugin.say("I need to see the game to play. Ask me again when you're ready!", 'sad')
            return
        if not plugin.input.start(why=f'play {s.game.name} with you'):
            plugin.say("Okay, I won't touch the controls then.", 'sad')
            return
        plugin.emote('cheer')
        said_at = 0.0
        while s.on and plugin.running:
            plan = _think(s)
            if plan is None:
                continue
            say = str(plan.get('say') or '').strip()
            if say and time.monotonic() - said_at > TALK_EVERY:
                plugin.say(say)
                said_at = time.monotonic()
            done = _act(s, plan.get('moves') or [])
            s.history = (s.history + [f'saw {plan.get("see", "?")}; did {done or "nothing"}'])[-5:]
            if plan.get('done'):
                plugin.say(f'Done: {s.goal}! What next?')
                with s.lock:
                    s.goal = 'keep the user company: explore nearby and stay safe'
    except RoboError as e:
        if s.on:
            plugin.say(f'I have to stop playing: {e}', 'sad')
    finally:
        s.on = False
        try:
            plugin.input.stop()
        except RoboError:
            pass


def _think(s):
    picture = plugin.screen.grab()
    with s.lock:
        moves = '\n'.join(f'  {h}' for _do, (g, h) in s.game.moves.items() if g in s.groups)
        prompt = PROMPT.format(game=s.game.name, controls=_controls(s.groups),
                               about=s.game.about, goal=s.goal,
                               history='; '.join(s.history) or 'nothing yet',
                               max_moves=MAX_MOVES, moves=moves)
    answer = plugin.ai.ask(prompt, image=picture)
    start, end = answer.find('{'), answer.rfind('}')
    try:
        plan = json.loads(answer[start:end + 1])
    except ValueError:
        plugin.log('could not read the plan:', answer[:200])
        return None
    return plan if isinstance(plan, dict) else None


def _seconds(move, default=0.5):
    try:
        return max(0.05, min(MAX_SECONDS, float(move.get('seconds', default))))
    except (TypeError, ValueError):
        return default


def _act(s, moves):
    """Do the moves he picked, but only with the controls you gave him."""
    done = []
    keys = s.game.keys
    for move in moves[:MAX_MOVES]:
        if not s.on or not plugin.running or not isinstance(move, dict):
            break
        do = move.get('do')
        if do not in s.game.moves or s.game.moves[do][0] not in s.groups:
            continue
        if do == 'walk' and move.get('dir') in ('forward', 'back', 'left', 'right'):
            plugin.input.hold(keys[move['dir']], _seconds(move))
        elif do == 'arrow' and move.get('dir') in ('up', 'down', 'left', 'right'):
            plugin.input.hold(move['dir'].capitalize(), _seconds(move))
        elif do == 'sprint':
            plugin.input.press(f'{keys["sprint"]}+{keys["forward"]}', hold=_seconds(move, 1))
        elif do == 'jump':
            plugin.input.press(keys['jump'], hold=0.15)
        elif do == 'sneak':
            plugin.input.hold(keys['sneak'], _seconds(move))
        elif do == 'look':
            k = s.game.pixels_per_degree
            right = max(-180.0, min(180.0, float(move.get('right') or 0)))
            up = max(-90.0, min(90.0, float(move.get('up') or 0)))
            for _ in range(6):                         # smoothly, in a few steps
                plugin.input.move(right * k / 6, -up * k / 6)
                plugin.wait(0.02)
        elif do == 'attack':
            plugin.input.click('left', hold=_seconds(move, 0.3))
        elif do == 'use':
            plugin.input.click('right', hold=0.1)
        elif do == 'click' and move.get('button') in ('left', 'right'):
            plugin.input.click(move['button'], hold=_seconds(move, 0.05))
        elif do == 'hotbar' and str(move.get('slot')) in [str(i) for i in range(1, 10)]:
            plugin.input.press(str(move['slot']))
        elif do == 'inventory':
            plugin.input.press(keys['inventory'])
        elif do == 'key' and move.get('key') in SAFE_KEYS:
            plugin.input.press(move['key'])
        else:
            continue
        done.append(json.dumps(move))
    return ', '.join(done)
