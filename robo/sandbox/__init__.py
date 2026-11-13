"""Running tasks where they can't hurt your computer. Portable code only.

    permissions.py  Permissions: what a task may read, change and download
    backend.py      the contract an OS sandbox implements (+ PipeProcess helper)
    workspace.py    the task's own folder, staged copies, the change review
    broker.py       requests from inside the sandbox (downloads), checked
    approval.py     Approver: asking you before granting anything
    worker/         the code that runs INSIDE the sandbox (stdlib only)

The OS-specific sandboxes live with each platform (Linux: bubblewrap in
robo/platform/linux/sandbox.py) and are returned by Platform.sandbox().
robo.tasks.sandboxed.SandboxedTask ties it all together.
"""
from .approval import Approver, DenyAll  # noqa: F401
from .backend import Limits, LaunchSpec, Mount, SandboxBackend, SandboxProcess  # noqa: F401
from .permissions import Permissions  # noqa: F401
from .workspace import ChangeSet, Workspace  # noqa: F401
