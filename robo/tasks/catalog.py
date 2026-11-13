"""The tasks Robo knows how to do.

'agent' is the real one: an AI agent (Claude Code with your login) does what
you ask, using only Robo's sandboxed tools (see agent_task.py).

Every real task runs in the sandbox (robo.tasks.sandboxed.SandboxedTask):
its code is a job in robo/sandbox/worker/jobs.py, and here is where you
say what it is called and which Permissions it needs. For now there is
only a placeholder that pretends to work for 1-2 minutes.

To add a task:
  1. write the job in robo/sandbox/worker/jobs.py (it runs inside the sandbox),
  2. add a factory here, with the Permissions it needs (default: none),
  3. teach the brain a phrase that replies action='start_task', action_arg='<kind>'.
"""
from .agent_task import AgentTask, TaskRefused, resolve_paths
from .base import Task
from .sandboxed import SandboxedTask, TaskEnvironment  # noqa: F401

PLACEHOLDER_SECONDS = (60.0, 120.0)


class TimerTask(Task):
    """In-process stand-in that just waits. Used by tests; runs no code."""
    kind = 'timer'

    def __init__(self, seconds, title='a timer'):
        super().__init__(title)
        self.seconds = seconds

    def is_done(self, now):
        return self.worked_seconds(now) >= self.seconds

    def progress(self, now):
        return min(1.0, self.worked_seconds(now) / self.seconds)


def _placeholder(rng, env, args):
    seconds = args.get('seconds') or rng.uniform(*PLACEHOLDER_SECONDS)
    return SandboxedTask('placeholder', 'a top secret task', env, args={'seconds': seconds})


def _agent(rng, env, args):
    """A task for the AI agent: args = {'goal': ..., 'read': [paths], 'write': [paths]}.
    Raises TaskRefused if it can't be done (no agent, a path missing / not allowed)."""
    goal = ' '.join(str(args.get('goal') or '').split())
    if not goal:
        raise TaskRefused('I need to know what the task is')
    agent = env.agent_factory() if env.agent_factory else None
    if agent is None:
        raise TaskRefused('I need an AI brain for that (Settings, AI brain)')
    if not agent.supports_tasks:
        raise TaskRefused(f'{agent.name} {agent.tasks_unsupported}')
    return AgentTask(goal, env, read=resolve_paths(args.get('read')),
                     write=resolve_paths(args.get('write')), agent=agent)


# kind -> factory(rng, env: TaskEnvironment, args: dict) -> Task
TASK_KINDS = {
    'placeholder': _placeholder,
    'agent': _agent,              # done by the AI agent with Robo's sandboxed tools
}
DEFAULT_KIND = 'placeholder'


def make_task(kind, rng, env, args=None):
    factory = TASK_KINDS.get(kind or DEFAULT_KIND, TASK_KINDS[DEFAULT_KIND])
    return factory(rng, env, args or {})
