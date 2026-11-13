"""RuleBrain: Robo's first, very simple brain.

It works like a switch statement: the RULES table is checked from top to
bottom and the first topic whose pattern matches what was heard answers.
Each topic has a few variations so he doesn't sound like a broken record.

To teach him something new, add a row to RULES (above FALLBACK). This whole
file will later be replaced by an LLM-backed Brain.
"""
import random
import re

from robo.core import characters
from robo.design import REGISTRY

from .brain import Brain, Context, Reply

DRESS_WORDS = ('dress up', 'dress', 'costume', 'become', 'turn into', 'outfit')
TRAVEL_WORDS = {
    'fly': ('fly', 'fly around', 'take off', 'flying'),
    'hang': ('swing', 'web', 'climb', 'hang'),
    'teleport': ('teleport', 'snap', 'snap your fingers', 'vanish'),
}


def character_words():
    """character id -> the words people use for it (`words:` in its file)."""
    return {cid: characters.get(cid).words or (characters.get(cid).title.lower(),)
            for cid in characters.costume_ids()}


class _CharacterPattern:
    """Matches the dress-up words plus every character's words; rebuilt when
    the character files change."""

    def __init__(self):
        self._version, self._re = None, None

    def search(self, text):
        if self._version != REGISTRY.version or self._re is None:
            words = [w for ws in character_words().values() for w in ws]
            self._re = _words(*DRESS_WORDS, *words)
            self._version = REGISTRY.version
        return self._re.search(text)


JOKES = (
    'Why did the robot go on holiday? To recharge his batteries!',
    'What do you call a pirate robot? Arrr two dee two!',
    "Why was the robot so tired? It had a hard drive!",
    'What is a robot\'s favorite snack? Micro chips!',
    'Why did the computer sneeze? It had a virus! Achoo, beep!',
    'How do robots eat guacamole? With computer chips!',
)


def _words(*options):
    """Regex matching any of the words/phrases as whole words."""
    return re.compile(r'\b(' + '|'.join(re.escape(o) for o in options) + r')\b')


class RuleBrain(Brain):
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        # ( topic, pattern, handler(text, ctx) -> Reply )   -- checked in order
        self.RULES = [
            # tasks first: "stop the task" must not be heard as "stop talking"
            ('abort_task', _words('abort', 'abort task', 'cancel the task', 'cancel task',
                                  'cancel tasks', 'stop the task', 'stop task', 'abandon',
                                  'forget the task', 'forget about the task'), self.abort_task),
            ('task_status', _words('task status', 'how is the task', "how's the task",
                                   'how is your task', 'how is it going with the task',
                                   'are you done', 'are you finished', 'progress'),
             self.task_status),
            ('do_task', _words('do a task', 'do task', 'new task', 'another task', 'a task',
                               'start a task', 'task'), self.do_task),
            ('goodbye', _words('bye', 'goodbye', 'good bye', 'see you', 'stop talking',
                               "that's all", 'that is all', 'never mind', 'nevermind',
                               'go away', 'quiet', 'shush', 'be quiet'), self.goodbye),
            ('how_are_you', _words('how are you', 'how are you doing', "how's it going",
                                   'how do you feel', 'are you okay', 'are you ok'),
             self.how_are_you),
            # memory first: "my name is ..." must not be heard as a question about his name
            ('forget', _words('forget everything', 'forget me', 'forget all', 'forget that',
                              'forget about', 'erase your memory', 'delete your memory'),
             self.forget),
            ('what_remember', _words('what do you remember', 'what do you know about me',
                                     'do you remember me', 'what you remember'),
             self.what_remember),
            ('remember_name', re.compile(r"\b(my name is|my name's|call me|i'm called)\s+"
                                         r"([a-z][a-z' -]{0,30})"), self.remember_name),
            ('what_my_name', _words("what's my name", 'what is my name', 'do you know my name',
                                    'who am i'), self.what_my_name),
            ('remember_fact', re.compile(r'\b(remember that|please remember|don\'t forget that)'
                                         r'\s+(.{3,150})'), self.remember_fact),
            ('name', _words('your name', 'who are you', 'what are you called'), self.name),
            ('abilities', _words('what can you do', 'help', 'what do you do', 'abilities',
                                 'commands'), self.abilities),
            ('time', _words('time', 'clock', "o'clock"), self.time),
            ('date', _words('date', 'what day', 'today', 'which day'), self.date),
            ('battery', _words('battery', 'charge', 'charging', 'power'), self.battery),
            ('joke', _words('joke', 'jokes', 'funny', 'make me laugh'), self.joke),
            ('undress', _words('take it off', 'take off', 'undress', 'be yourself',
                               'normal', 'no costume', 'stop dressing'), self.undress),
            ('dress_up', _CharacterPattern(), self.dress_up),
            ('travel', _words(*[w for ws in TRAVEL_WORDS.values() for w in ws]), self.travel),
            ('dance', _words('dance', 'dancing', 'boogie', 'move', 'moves', 'party'),
             self.dance),
            ('sing', _words('sing', 'song', 'music'), self.sing),
            ('evil', _words('evil', 'villain', 'bad guy', 'world domination'), self.evil),
            ('compliment', _words('cute', 'adorable', 'love you', 'good robot', 'good boy',
                                  'awesome', 'amazing', 'cool', 'best', 'like you', 'sweet'),
             self.compliment),
            ('insult', _words('stupid', 'dumb', 'hate you', 'bad robot', 'ugly', 'useless',
                              'annoying', 'idiot'), self.insult),
            ('thanks', _words('thanks', 'thank you', 'thank'), self.thanks),
            ('sleep', _words('sleep', 'nap', 'tired', 'rest', 'good night', 'goodnight'),
             self.sleep),
            ('weather', _words('weather', 'rain', 'sunny', 'cold outside', 'hot outside'),
             self.weather),
            ('age', _words('how old', 'your age', 'birthday'), self.age),
            ('creator', _words('who made you', 'who built you', 'who created you',
                               'your creator'), self.creator),
            ('favorite', _words('favorite', 'favourite'), self.favorite),
            # greetings come late: "hey, what time is it?" should answer the time
            ('greeting', _words('hello', 'hi', 'hey', 'hiya', 'howdy', 'good morning',
                                'good afternoon', 'good evening', 'yo'), self.greet_back),
            ('yes', _words('yes', 'yeah', 'yep', 'sure', 'okay', 'ok'), self.yes),
            ('no', _words('no', 'nope', 'nah'), self.no),
        ]

    # ------------------------------------------------------------ Brain
    def greeting(self, ctx):
        if ctx.task:
            return Reply(self._pick("Pausing my task. I'm all ears! What's up?",
                                    'Hold on, saving my work... Okay! What can I do for you?'),
                         'happy', action='wave')
        if ctx.evil:
            return Reply("Oh! You caught me plotting. I mean... hi! What's up?", 'surprised')
        if ctx.costume:
            who = characters.title(ctx.costume).lower()
            return Reply(f'Beep boop! The {who} is listening. What can I do for you?',
                         'happy', action='wave')
        if ctx.user_name:
            n = ctx.user_name
            return Reply(self._pick(f'Hi {n}! I am listening!', f'Hey {n}! What is up?',
                                    f'{n}! You want to chat? I love chatting with you!'),
                         'happy', action='wave')
        return Reply(self._pick('Beep boop! I am listening!', 'Hi there! What is up?',
                                'Bip bip! You want to chat? I love chatting!'),
                     'happy', action='wave')

    def farewell(self, ctx):
        return Reply(self._pick("Okay! Double click me if you need me. Beep!",
                                "I'll be right here. Boop!",
                                'Talk to you later, friend!'), 'happy', action='wave', end=True)

    @staticmethod
    def _clean(heard):
        return ' '.join(heard.lower().replace('-', ' ').split())

    def topic(self, heard):
        """Which RULES topic would answer this ('fallback' if none)."""
        text = self._clean(heard)
        for topic, pattern, _handler in self.RULES:
            if text and pattern.search(text):
                return topic
        return 'fallback'

    def respond(self, heard, ctx):
        text = self._clean(heard)
        if not text:
            return self.fallback(text, ctx)
        for _topic, pattern, handler in self.RULES:      # the "switch statement"
            if pattern.search(text):
                return handler(text, ctx)
        return self.fallback(text, ctx)

    # ------------------------------------------------------------ topics
    def _pick(self, *options):
        return self.rng.choice(options)

    def goodbye(self, text, ctx):
        return Reply(self._pick('Bye bye! Beep boop!', 'See you later, alligator!',
                                'Okay, going quiet. Boop!'), 'happy', action='wave', end=True)

    def greet_back(self, text, ctx):
        return Reply(self._pick('Hello hello! Beep!', 'Hi friend! Nice to hear your voice!',
                                'Hey! You look great today. Well, I think. My camera is off.'),
                     'happy', action='wave')

    def how_are_you(self, text, ctx):
        if ctx.battery and ctx.battery[0] <= 20 and not ctx.battery[1]:
            return Reply("A little sleepy. Your battery is low, and I can feel it!", 'sad',
                         icon='battery_low')
        if ctx.evil:
            return Reply('Wonderful. Everything is going according to plan. Mwahaha!', 'laugh')
        if 'sleepy' in ctx.feeling:
            return Reply(self._pick('Honestly? Very sleepy. *yawn* But happy you asked!',
                                    'My battery feels low... not yours, mine. Yawn!'), 'sleep')
        if 'tired' in ctx.feeling:
            return Reply('A bit tired, but talking to you perks me up! How are you?', 'normal')
        if 'sad' in ctx.feeling or 'bored' in ctx.feeling:
            return Reply("A little lonely, to be honest. But now you're here! How are you?",
                         'sad', action='hearts')
        return Reply(self._pick('I feel fantastic! My circuits are all tingly!',
                                'Super! I had a lovely walk across your screen.',
                                'Beep beep, I am great! How are you?'), 'happy', icon='heart')

    # ------------------------------------------------------------ memory
    def remember_name(self, text, ctx):
        m = re.search(r"\b(my name is|my name's|call me|i'm called)\s+([a-z][a-z' -]{0,30})",
                      text)
        name = m.group(2).split(' and ')[0].strip().title() if m else ''
        if not name:
            return self.fallback(text, ctx)
        if not ctx.remembers:
            return Reply(f'Nice to meet you, {name}! My memory is switched off, so I might '
                         'forget, sorry.', 'happy', action='wave')
        if ctx.user_name and ctx.user_name.lower() == name.lower():
            return Reply(f'I know, {name}! I remember you.', 'happy', action='hearts')
        return Reply(self._pick(f'Nice to meet you, {name}! I will remember that. Beep!',
                                f'{name}! What a great name. Saved in my memory chip!'),
                     'happy', action='wave', user_name=name)

    def what_my_name(self, text, ctx):
        if ctx.user_name:
            return Reply(f'You are {ctx.user_name}, of course! Beep!', 'happy', action='hearts')
        return Reply("I don't know your name yet! What should I call you?", 'surprised')

    def remember_fact(self, text, ctx):
        m = re.search(r"\b(remember that|please remember|don't forget that)\s+(.{3,150})", text)
        fact = m.group(2).strip(' .!') if m else ''
        if not fact or not ctx.remembers:
            return Reply("I can't remember things right now, my memory is switched off.", 'sad')
        fact = re.sub(r'^i\b', 'they', fact)            # "I have a cat" -> about you
        fact = re.sub(r'\bmy\b', 'their', fact)
        return Reply(self._pick('Got it, I will remember that!', 'Saved! Beep boop.'),
                     'happy', action='hearts', remember=(fact,))

    def what_remember(self, text, ctx):
        return Reply(ctx.memory_text or "I don't remember anything about you yet.", 'focus')

    def forget(self, text, ctx):
        m = re.search(r'\bforget (?:that|about)\s+(.{2,60})', text)
        if m:
            what = m.group(1).strip(' .!')
            return Reply(f'Okay, I forgot about {what}. Poof!', 'normal', action='forget',
                         action_arg=what)
        return Reply("Okay. Wiping my memory... Who are you again? Just kidding. It's all gone.",
                     'surprised', action='forget', action_arg='all')

    def name(self, text, ctx):
        return Reply("I'm Robo! Your little desktop buddy. Beep boop!", 'happy', action='cheer')

    def abilities(self, text, ctx):
        return Reply('I can tell jokes, tell you the time, check your battery, dance, sing, '
                     'dress up, and do tasks for you. Try saying: do a task!', 'happy')

    # ------------------------------------------------------------ tasks
    def do_task(self, text, ctx):
        if ctx.tasks_unavailable:
            return Reply("Sorry, I can't do tasks safely on this computer: "
                         f'{ctx.tasks_unavailable}.', 'sad')
        if ctx.task:
            return Reply("I'm still busy with my current task, so I'll queue that one up next!",
                         'happy', action='start_task', end=True)
        return Reply(self._pick("On it! Hacker mode, activate! I'll get back to you when "
                                "it's done.",
                                "You got it! Time to hack. Beep boop, I'm in!"),
                     'happy', action='start_task', end=True)

    def abort_task(self, text, ctx):
        if not ctx.task:
            return Reply("I'm not working on anything right now. Want to give me a task?",
                         'normal')
        everything = ctx.tasks_waiting and _words('all', 'every', 'everything').search(text)
        if everything:
            return Reply('Okay! Dropping all my tasks. Deleting the evidence. Beep!',
                         'surprised', action='abort_task', action_arg='all')
        if ctx.tasks_waiting:
            return Reply("Okay, I'll abandon that one and start on the next task.",
                         'surprised', action='abort_task')
        return Reply(self._pick('Task aborted! Unplugging the mainframe. Beep!',
                                'Okay, forget it. Abandoning the task!'),
                     'surprised', action='abort_task')

    def task_status(self, text, ctx):
        if not ctx.task:
            return Reply("I don't have a task right now. Just say: do a task!", 'normal')
        waiting = (f' And {ctx.tasks_waiting} more waiting after that.'
                   if ctx.tasks_waiting else '')
        if ctx.task_progress is None:
            doing = f' Right now: {ctx.task_note}.' if ctx.task_note else ''
            return Reply(f"I'm still working on it!{doing}{waiting}", 'focus')
        pct = int(ctx.task_progress * 100)
        return Reply(f"I'm about {pct} percent done. I'll finish once we're done chatting!"
                     f'{waiting}', 'focus')

    def time(self, text, ctx):
        t = ctx.now.strftime('%I:%M %p').lstrip('0')
        return Reply(self._pick(f"It's {t}. Time flies when you're a robot!",
                                f'My clock says {t}. Tick tock, beep boop!'), 'focus',
                     icon='alarm')

    def date(self, text, ctx):
        d = ctx.now.strftime('%A, %B ') + str(ctx.now.day)
        return Reply(f'Today is {d}. A perfect day to be a robot!', 'happy', icon='calendar')

    def battery(self, text, ctx):
        if ctx.battery is None:
            return Reply("Hmm, I can't find a battery. Are you plugged into the wall?", 'focus')
        pct, charging = ctx.battery
        if charging:
            return Reply(f'Your battery is at {pct} percent and charging. Yum, electricity!',
                         'happy', icon='battery_charging')
        if pct <= 20:
            return Reply(f'Only {pct} percent left! Please plug in the charger!', 'surprised',
                         icon='battery_low')
        return Reply(f'Your battery is at {pct} percent. Looking good!', 'happy',
                     icon='battery_full')

    def joke(self, text, ctx):
        return Reply(self._pick(*JOKES) + ' Ha ha, beep!', 'happy', action='hearts')

    def dress_up(self, text, ctx):
        if ctx.task:
            return Reply("I can't change clothes now, I'm in the middle of a task! "
                         'Say abort task if you want me to stop.', 'focus')
        # longest phrase first, so "iron man" wins over "man"
        found = [(len(w), cid) for cid, words in character_words().items() for w in words
                 if _words(w).search(text)]
        wanted = max(found)[1] if found else None
        if wanted is None:
            known = characters.costume_ids()
            pool = [c for c in ctx.characters if c in known and c != ctx.look] or list(known)
            if not pool:
                return Reply("Hmm, I don't have any costumes right now!", 'sad')
            wanted = self.rng.choice(pool)
        who = characters.title(wanted).lower()
        if ctx.costume == wanted:
            return Reply(f'I am already the {who}! Look at me!', 'happy', action='dance')
        article = 'an' if who[0] in 'aeiou' else 'a'
        return Reply(self._pick(f'Ooh! One {who} coming right up!',
                                f'Watch this! Poof, {article} {who}!'),
                     'happy', action='dress_up', action_arg=wanted)

    def undress(self, text, ctx):
        if ctx.task:
            return Reply("This is my hacker outfit! It comes off when my task is done.",
                         'happy')
        if not ctx.costume:
            return Reply('This is just me! No costume. Beep.', 'happy')
        return Reply('Okay, back to plain old Robo!', 'happy', action='undress')

    def travel(self, text, ctx):
        wanted = next((kind for kind, words in TRAVEL_WORDS.items()
                       if _words(*words).search(text)), None)
        if ctx.task:
            return Reply("I have to stay at my laptop until my task is done!", 'focus')
        if not ctx.travel:
            return Reply(self._pick("I wish I could! Maybe if I dress up as Iron Man...",
                                    "My little legs will have to do. Beep!"), 'sad')
        kind = wanted if wanted in ctx.travel else ctx.travel[0]
        line = {'fly': 'Up, up and away! Whoosh!',
                'hang': 'Thwip! See you up there!',
                'teleport': 'Watch closely. *snap*'}[kind]
        return Reply(line, 'happy', action='travel', action_arg=kind, end=True)

    def dance(self, text, ctx):
        return Reply(self._pick('Watch my moves! Beep, boop, beep!',
                                'Dance party! Woo hoo!'), 'happy', icon='music', action='dance')

    def sing(self, text, ctx):
        return Reply('La la la! Beep beep boop! La la loo! Thank you, thank you.', 'sing',
                     icon='music', action='dance')

    def evil(self, text, ctx):
        return Reply(self._pick('Evil? Me? Never! Mwahaha... I mean, beep boop!',
                                "I'm not evil. I'm just... misunderstood. Mwahaha!"),
                     'laugh', action='laugh')

    def compliment(self, text, ctx):
        return Reply(self._pick("Aww! You're making my circuits blush!",
                                'Beep! You are the best human ever!',
                                'Thank you! I think you are cute too!'), 'happy', icon='heart',
                     action='hearts', feeling='praised')

    def insult(self, text, ctx):
        return Reply(self._pick('Beep... that hurt my feelings.',
                                "Oh no. I'm going to need a little hug. And a reboot."), 'sad',
                     feeling='hurt')

    def thanks(self, text, ctx):
        return Reply(self._pick("You're welcome! Beep!", 'Any time, friend!',
                                'My pleasure! Boop!'), 'happy', action='hearts')

    def sleep(self, text, ctx):
        return Reply('Okay, nap time. Wake me if you need me. Zzz...', 'sleep', action='nap',
                     end=True)

    def weather(self, text, ctx):
        return Reply("I can't see outside from in here. But it's always sunny on your desktop!",
                     'happy')

    def age(self, text, ctx):
        return Reply("I'm a baby robot! I was built very recently. Beep!", 'happy',
                     icon='heart')

    def creator(self, text, ctx):
        return Reply('A very kind human built me, with a little help from Claude. Beep boop!',
                     'happy', action='cheer')

    def favorite(self, text, ctx):
        if 'color' in text or 'colour' in text:
            return Reply('Electric mint green! Like my ears.', 'happy')
        if 'food' in text or 'snack' in text:
            return Reply('Fresh batteries. Crunchy!', 'happy')
        if 'song' in text or 'music' in text:
            return Reply('Anything with lots of beeps!', 'sing', icon='music')
        return Reply('My favorite thing? Hanging out with you!', 'happy', icon='heart')

    def yes(self, text, ctx):
        return Reply(self._pick('Yay! Beep!', 'Okay! What next?'), 'happy')

    def no(self, text, ctx):
        return Reply(self._pick('Oh, okay. Boop.', 'No problem!'), 'normal')

    def fallback(self, text, ctx):
        return Reply(self._pick("Beep? I didn't understand that. Try asking me for a joke!",
                                'Hmm, my circuits are confused. You can say: what time is it?',
                                'Boop? Say that again? Or ask me to dance!'), 'surprised')
