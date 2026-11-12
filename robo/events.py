"""Events: the one thing every event source hands to the robot.

An event source (battery, notifications, ...) only has to produce an
`Event` with one of the KINDS below; the robot picks the matching icon.
`classify()` turns the text of a desktop notification into a kind and is
shared by every platform.
"""
from dataclasses import dataclass
from typing import Callable

# Every kind has an icon in robo.render.icons.ICONS.
KINDS = (
    'battery_low', 'battery_charging', 'battery_full', 'update', 'reboot',
    'mail', 'chat', 'wifi', 'wifi_off', 'download', 'calendar', 'alarm',
    'bell', 'warning', 'music', 'camera', 'bluetooth', 'usb', 'heart',
)
FALLBACK_KIND = 'bell'

# Kinds that both the OS and our own watchers may report (e.g. GNOME's
# "battery low" notification and our battery check): shown once per minute.
SYSTEM_KINDS = frozenset({'battery_low', 'battery_charging', 'battery_full',
                          'wifi', 'wifi_off', 'update', 'reboot'})


@dataclass(frozen=True)
class Event:
    kind: str
    source: str = 'notification'   # who reported it: 'notification', 'system', 'demo'
    detail: str = ''               # human readable, for the log only


EventSink = Callable[[Event], None]


# ---------------------------------------------------------------- classify
# Checked in order; first match wins.
KEYWORD_RULES = [
    ('battery_low', ['battery low', 'low battery', 'battery is low', 'battery critical',
                     'critically low', 'power low', 'battery almost']),
    ('battery_full', ['fully charged', 'battery full', 'battery is full']),
    ('battery_charging', ['charging', 'charger connected', 'plugged in']),
    ('reboot', ['restart required', 'reboot required', 'restart to', 'restart your',
                'reboot']),
    ('update', ['update', 'upgrade', 'refresh', 'new version', 'gnome-software',
                'software']),
    ('download', ['download', 'transfer complete', 'file received']),
    ('mail', ['mail', 'inbox', 'thunderbird', 'evolution', 'geary', 'outlook']),
    ('calendar', ['calendar', 'meeting', 'appointment', 'agenda', 'starts in', 'event']),
    ('alarm', ['alarm', 'timer', 'reminder']),
    ('chat', ['message', 'telegram', 'slack', 'discord', 'signal', 'whatsapp', 'teams',
              'element', 'chat', 'mentioned', 'replied', 'sent you']),
    ('camera', ['screenshot', 'screen recording', 'screencast']),
    ('music', ['spotify', 'rhythmbox', 'now playing', 'music', 'lollypop', 'song']),
    ('bluetooth', ['bluetooth', 'paired']),
    ('usb', ['usb', 'mounted', 'removable', 'drive', 'device']),
    ('wifi_off', ['disconnected', 'connection lost', 'offline', 'no internet',
                  'network unavailable', 'connection failed']),
    ('wifi', ['wi-fi', 'wifi', 'network', 'connected', 'connection established']),
    ('warning', ['error', 'failed', 'failure', 'warning', 'critical', 'problem', 'crash',
                 'not enough', 'low disk', 'disk space']),
]

# freedesktop notification "category" hints (prefix match).
CATEGORY_RULES = [
    ('email', 'mail'), ('im', 'chat'), ('presence', 'chat'), ('call', 'chat'),
    ('transfer.error', 'warning'), ('transfer', 'download'),
    ('network.disconnected', 'wifi_off'), ('network.error', 'wifi_off'),
    ('network', 'wifi'), ('device.error', 'warning'), ('device', 'usb'),
]


def classify(app, summary, body, category='', urgent=False):
    """Pick the event kind for a desktop notification."""
    category = (category or '').lower()
    for prefix, kind in CATEGORY_RULES:
        if category == prefix or category.startswith(prefix + '.'):
            return kind
    text = ' '.join([app or '', summary or '', body or '']).lower()
    for kind, words in KEYWORD_RULES:
        if any(w in text for w in words):
            return kind
    return 'warning' if urgent else FALLBACK_KIND
