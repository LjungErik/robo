"""OS-specific back ends. See base.py for the contract a port must fulfil."""
import sys


def load_platform(name=None):
    """Return the Platform for this OS (or the one named, e.g. 'headless')."""
    name = name or sys.platform
    if name == 'headless':
        from .headless import HeadlessPlatform
        return HeadlessPlatform()
    if name.startswith('linux'):
        from .linux import LinuxPlatform
        return LinuxPlatform()
    # Future ports go here, e.g.:
    #   if name == 'win32':  from .windows import WindowsPlatform; return WindowsPlatform()
    #   if name == 'darwin': from .macos import MacPlatform; return MacPlatform()
    raise NotImplementedError(
        f'Robo has no back end for {name!r} yet — see robo/platform/base.py to write one.')
