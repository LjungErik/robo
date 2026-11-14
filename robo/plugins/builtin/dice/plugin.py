"""The smallest example plugin. Copy this folder to ~/.config/robo/plugins/
to start your own; Robo reloads it every time you save."""
import random
import re

from robo_plugin import plugin


@plugin.command('flip a coin', 'heads or tails', 'toss a coin')
def flip(text):
    plugin.emote('cheer')
    return random.choice(['Heads!', 'Tails!'])


@plugin.command('roll a dice', 'roll a die', 'roll the dice', 'roll dice')
def roll(text):
    sides = int((re.search(r'(\d+)[- ]sided', text) or [0, 6])[1])
    return f'I rolled a {random.randint(1, max(2, sides))}!'


@plugin.tool('roll_dice', 'Roll a dice for the user', sides='how many sides (default 6)')
def roll_tool(sides=6):
    return f'It landed on {random.randint(1, max(2, int(sides)))}.'


@plugin.menu('🎲  Roll a dice')
def roll_menu():
    return f'I rolled a {random.randint(1, 6)}!'
