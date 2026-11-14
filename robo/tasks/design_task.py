"""DesignTask: Robo designs a brand-new outfit for himself, with his AI agent.

It is an AgentTask (the agent's CLI runs outside the sandbox with all of
its own tools switched off; its only tools are Robo's sandboxed ones), but
it gets none of your files. All it can read is a "design kit" Robo puts
together:

    input/outfit-kit/README.md      how character files work
    input/outfit-kit/examples/      a few finished outfits to learn from
    input/outfit-kit/taken.txt      outfits that already exist (make something new)
    input/outfit-kit/check.py       the checker: draws every pose, writes a preview
    input/outfit-kit/robo/          Robo's own code, for the checker

It writes the new file to files/results/, checks it and looks at the
preview picture (look_at_image) until it's happy. Robo then checks it again
himself, outside the sandbox, and only a file that loads cleanly, is a
costume and draws without a single problem is installed, into
~/.config/robo/characters/robo-made/. Character files are only interpreted
(shapes and small expressions, never code), so a design can at worst look
odd. Nothing to review, nothing of yours involved, so it doesn't ask first.
"""
import logging
import os
import shutil
import time

from robo.sandbox import Permissions

from .agent_task import AgentTask

log = logging.getLogger(__name__)

DESIGN_SECONDS = 15 * 60
MAX_DESIGNS = 1                    # outfits installed per task
EXAMPLES = ('robo.yaml', 'pirate.yaml', 'wizard.yaml', 'kitty.yaml', 'ironman.yaml')
_PACKAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # robo/
BUILTIN_CHARACTERS = os.path.join(_PACKAGE, 'characters')

CHECK_SCRIPT = '''\
"""Check an outfit file and draw a preview of every pose:
    python3 input/outfit-kit/check.py files/results/<id>.yaml
It prints problems (fix every one) and writes files/results/<id>.preview.png."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from robo.design.check import check  # noqa: E402

sys.exit(1 if check(sys.argv[1:]) else 0)
'''

BRIEF = """\
Design a brand-new outfit for Robo (that's you!) to dress up in. {idea}

How:
1. Read input/outfit-kit/README.md (the file format: layers, shapes, colours, \
gestures, particles, personality) and look at the examples in \
input/outfit-kit/examples/ (robo.yaml is the robot you draw on: read its coordinates).
2. Pick something that is NOT in input/outfit-kit/taken.txt. Give it a short lowercase \
`id` (letters and underscores) and a fun `name`.
3. Write it to files/results/<id>.yaml as a costume. Include: `words` (what people say \
to ask for it), `wear` (two to four situations it suits, from the README), a `move` \
(signature move, with gestures you define or ones from the examples), a `demand` \
icon, `layers` that make it instantly recognisable even at small size (anything he \
holds goes in front_hand; read "Holding things" in the README so it isn't hidden \
behind his body or head), and a short \
`personality` (speech, a few traits, two or three `lines` of each of: dressed_up, \
remark, bored).
4. Run: python3 input/outfit-kit/check.py files/results/<id>.yaml \
and fix every problem it reports until it says ok.
5. Look at files/results/<id>.preview.png with look_at_image. Is it cute, clear and \
well placed in every pose (walking, sitting, flying, evil)? Improve it and check again.
It must be a new idea, not a variation: nothing in taken.txt may be the same kind of \
character (no second weather god, detective or duck under another name).
Only one outfit. When you're done, say in one or two spoken sentences what you made \
and what you call it, as Robo, excited."""


class DesignTask(AgentTask):
    kind = 'design'

    def __init__(self, env, agent, designs_dir, idea='', taken=()):
        idea = ' '.join(str(idea or '').split())[:200]
        title = f'designing {idea}' if idea else 'designing a new outfit'
        super().__init__(title, env, agent=agent)
        self.title = title[:48]
        self.idea = idea
        self.taken = tuple(taken)
        self.designs_dir = designs_dir
        self.permissions = Permissions(max_seconds=DESIGN_SECONDS)
        self.goal = BRIEF.format(idea=(f'The idea: {idea}.' if idea else
                                       'What it is is up to you: surprise us!'))
        self.kit = None
        self.designed = []             # ids installed when it's done
        self.problems = []             # why a design was turned down

    # ------------------------------------------------------------ the kit
    def approval_lines(self):
        return [f'Design: {self.idea or "a new outfit of his own"}',
                f'With: {self.agent.name if self.agent else "?"} (only Robo\'s own outfit '
                'files and code; none of yours; no internet)',
                f'The new outfit goes to: {self.designs_dir}']

    def on_start(self, now):
        try:
            self.kit = self._make_kit()
        except OSError as e:
            self.fail(now, f'could not prepare the design kit: {e}')
            return
        self.permissions = Permissions(read=(self.kit,), max_seconds=DESIGN_SECONDS)
        self.trusted = (self.kit,)
        super().on_start(now)

    def _make_kit(self):
        root = os.path.join(self.env.workspace_root, f'kit-{self.id}')
        kit = os.path.join(root, 'outfit-kit')
        shutil.rmtree(root, ignore_errors=True)
        os.makedirs(os.path.join(kit, 'examples'), mode=0o700)
        shutil.copy(os.path.join(BUILTIN_CHARACTERS, 'README.md'), kit)
        for name in EXAMPLES:
            src = os.path.join(BUILTIN_CHARACTERS, name)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(kit, 'examples'))
        with open(os.path.join(kit, 'taken.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(self.taken) + '\n')
        with open(os.path.join(kit, 'check.py'), 'w', encoding='utf-8') as f:
            f.write(CHECK_SCRIPT)
        shutil.copytree(_PACKAGE, os.path.join(kit, 'robo'),
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.preview.png'))
        return kit

    def _prompt(self):
        return f'The task: {self.goal}'

    # ------------------------------------------------------------ the result
    def is_done(self, now):
        if not super().is_done(now):
            return False
        self._install(os.path.join(self.workspace.work, 'files', 'results'))
        if not self.designed:
            why = self.problems[0] if self.problems else 'no outfit file was made'
            self.fail(now, f"the design didn't work out: {why}")
            return False
        return True

    def on_done(self, now):
        self._stop()
        self._discard()                # it's installed: the workspace isn't needed any more
        self._remove_kit()

    def on_abort(self, now):
        super().on_abort(now)
        self._remove_kit()

    def on_fail(self, now):
        super().on_fail(now)
        self._remove_kit()

    def _remove_kit(self):
        if self.kit:
            shutil.rmtree(os.path.dirname(self.kit), ignore_errors=True)

    def _install(self, results):
        try:
            names = sorted(n for n in os.listdir(results) if n.endswith(('.yaml', '.yml')))
        except OSError:
            names = []
        for name in names[:MAX_DESIGNS * 3]:
            if len(self.designed) >= MAX_DESIGNS:
                break
            cid = install_design(os.path.join(results, name), self.designs_dir,
                                 self.problems, idea=self.idea)
            if cid:
                self.designed.append(cid)


def install_design(path, designs_dir, problems, idea=''):
    """Check a design and copy it into designs_dir. Returns its id, or None
    (and the reason in `problems`)."""
    from robo.design.sharing import install
    stamp = time.strftime('%Y-%m-%d')
    header = f'# Designed by Robo himself on {stamp}' + (f' ({idea})' if idea else '') + '.\n'
    cid = install(path, designs_dir, problems, header=header)
    if cid:
        log.info('installed his own design %s', cid)
    return cid


def designs(designs_dir):
    """The outfits he designed himself: [(id, path)]."""
    try:
        names = sorted(os.listdir(designs_dir))
    except OSError:
        return []
    return [(os.path.splitext(n)[0], os.path.join(designs_dir, n))
            for n in names if n.endswith(('.yaml', '.yml')) and not n.startswith('.')]
