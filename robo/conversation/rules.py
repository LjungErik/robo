"""RuleBrain: Robo's first, very simple brain.

It works like a switch statement: the RULES table is checked from top to
bottom and the first topic whose pattern matches what was heard answers.
Each topic has a few variations so he doesn't sound like a broken record.

To teach him something new, add a row to RULES (above FALLBACK). This whole
file will later be replaced by an LLM-backed Brain.
"""
import random
import re

from robo.core.characters import CHARACTERS

from .brain import Brain, Context, Reply

# Words people use for each character (speech recognition hears plain words).
CHARACTER_WORDS = {
    'pharaoh': ('pharaoh', 'egypt', 'egyptian', 'king'),
    'cowboy': ('cowboy', 'cow boy', 'sheriff'),
    'viking': ('viking',),
    'accountant': ('accountant', 'accounting'),
    'mechanic': ('mechanic',),
    'roman': ('roman', 'emperor', 'caesar'),
    'chef': ('chef', 'cook'),
    'astronaut': ('astronaut', 'space', 'spaceman'),
    'wizard': ('wizard', 'magician', 'witch'),
    'pirate': ('pirate',),
    'superhero': ('superhero', 'super hero', 'hero'),
    'kitty': ('kitty', 'cat', 'kitten'),
}

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
            ('name', _words('your name', 'who are you', 'what are you called'), self.name),
            ('abilities', _words('what can you do', 'help', 'what do you do', 'abilities',
                                 'commands'), self.abilities),
            ('time', _words('time', 'clock', "o'clock"), self.time),
            ('date', _words('date', 'what day', 'today', 'which day'), self.date),
            ('battery', _words('battery', 'charge', 'charging', 'power'), self.battery),
            ('joke', _words('joke', 'jokes', 'funny', 'make me laugh'), self.joke),
            ('undress', _words('take it off', 'take off', 'undress', 'be yourself',
                               'normal', 'no costume', 'stop dressing'), self.undress),
            ('dress_up', _words('dress up', 'dress', 'costume', 'become', 'turn into',
                                'outfit', *[w for ws in CHARACTER_WORDS.values() for w in ws]),
             self.dress_up),
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
            who = CHARACTERS[ctx.costume].title.lower()
            return Reply(f'Beep boop! The {who} is listening. What can I do for you?',
                         'happy', action='wave')
        return Reply(self._pick('Beep boop! I am listening!', 'Hi there! What is up?',
                                'Bip bip! You want to chat? I love chatting!'),
                     'happy', action='wave')

    def farewell(self, ctx):
        return Reply(self._pick("Okay! Double click me if you need me. Beep!",
                                "I'll be right here. Boop!",
                                'Talk to you later, friend!'), 'happy', action='wave', end=True)

    def respond(self, heard, ctx):
        text = ' '.join(heard.lower().replace('-', ' ').split())
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
        return Reply(self._pick('I feel fantastic! My circuits are all tingly!',
                                'Super! I had a lovely walk across your screen.',
                                'Beep beep, I am great! How are you?'), 'happy', icon='heart')

    def name(self, text, ctx):
        return Reply("I'm Robo! Your little desktop buddy. Beep boop!", 'happy', action='cheer')

    def abilities(self, text, ctx):
        return Reply('I can tell jokes, tell you the time, check your battery, dance, sing, '
                     'dress up, and do tasks for you. Try saying: do a task!', 'happy')

    # ------------------------------------------------------------ tasks
    def do_task(self, text, ctx):
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
            return Reply(f"I'm still working on it!{waiting}", 'focus')
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
        wanted = next((cid for cid, words in CHARACTER_WORDS.items()
                       if _words(*words).search(text)), None)
        if wanted is None:
            pool = list(ctx.characters) or list(CHARACTERS)
            wanted = self.rng.choice(pool)
        who = CHARACTERS[wanted].title.lower()
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
                     action='hearts')

    def insult(self, text, ctx):
        return Reply(self._pick('Beep... that hurt my feelings.',
                                "Oh no. I'm going to need a little hug. And a reboot."), 'sad')

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
