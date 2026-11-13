"""The tasks Robo knows how to do.

For now there is only a placeholder that pretends to work for 1-2 minutes.
To add a real task: subclass robo.tasks.Task, register a factory in
TASK_KINDS, and teach the brain a phrase that replies with
action='start_task', action_arg='<kind>'.
"""
from .base import Task

PLACEHOLDER_SECONDS = (60.0, 120.0)


class PlaceholderTask(Task):
    """Pretends to work for a while. Stands in for real tasks."""
    kind = 'placeholder'

    def __init__(self, seconds, title='a top secret task'):
        super().__init__(title)
        self.seconds = seconds

    def is_done(self, now):
        return self.worked_seconds(now) >= self.seconds

    def progress(self, now):
        return min(1.0, self.worked_seconds(now) / self.seconds)

    def on_done(self, now):
        self.result = 'All done! I hacked the mainframe. Well, pretended to.'


# kind -> factory(rng) -> Task
TASK_KINDS = {
    'placeholder': lambda rng: PlaceholderTask(rng.uniform(*PLACEHOLDER_SECONDS)),
}
DEFAULT_KIND = 'placeholder'


def make_task(kind, rng):
    return TASK_KINDS.get(kind or DEFAULT_KIND, TASK_KINDS[DEFAULT_KIND])(rng)
