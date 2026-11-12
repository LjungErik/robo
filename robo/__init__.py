"""Robo — a tiny desktop companion robot.

Package layout:
    robo.core      the robot itself (behaviour, bubble, evil mode). Pure Python.
    robo.render    draws the robot and icons with Cairo.
    robo.platform  everything OS specific (window, notifications, battery, ...).
    robo.app       wires the three together and parses the command line.
"""
