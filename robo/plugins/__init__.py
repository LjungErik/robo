"""Plugins: new abilities for Robo, added and changed while he runs.

    manifest.py   plugin.json: id, name, permissions
    runner.py     one plugin's sandboxed process (start, reload, crash, stop)
    services.py   what plugins may ask Robo to do, behind their permissions
    manager.py    every plugin: finding, switching on/off, hot reload, routing
    builtin/      example plugins that come with Robo (off until you switch them on)

The plugin side is robo/sandbox/worker/robo_plugin.py (what a plugin imports)
and plugin_host.py (runs it). How to write one: robo/plugins/README.md.
"""
from .manager import BUILTIN_DIR, PluginManager  # noqa: F401
from .manifest import PERMISSIONS, ManifestError, load_manifest  # noqa: F401
from .services import Services  # noqa: F401
