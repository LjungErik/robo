"""The characters Robo can dress up as (or look like all the time).

They are not written in code any more: every character is a file in
robo/characters/ (or ~/.config/robo/characters/), read by robo.design.
This module is the core's view of them.

    get('pirate')      -> Character (demand, signature move, walk style, travel)
    costume_ids()      -> who he may dress up as
    look_ids()         -> what he may look like all the time (Settings → Look)
    demand_icons()     -> bubble icons characters demand
"""
from robo.design import REGISTRY, Character  # noqa: F401  (re-exported)

DEFAULT_LOOK = 'robo'


def get(cid):
    return REGISTRY.get(cid)


def costume_ids():
    return REGISTRY.costumes()


def look_ids():
    return REGISTRY.looks()


def demand_icons():
    return REGISTRY.demand_ids()


def title(cid):
    c = REGISTRY.get(cid)
    return c.title if c else cid
