"""GPT, through OpenAI's Codex CLI (`codex exec`).

Log in once with `codex login` using your ChatGPT account; Robo uses that
login. Runs in Codex's read-only sandbox, in Robo's own empty folder.

Written from the Codex CLI documentation; not yet tried against a real
installation (it wasn't installed where this was built).
"""
import os
import tempfile

from .base import AgentAnswer, AgentBackend, AgentError, AgentStatus


class Codex(AgentBackend):
    id = 'codex'
    name = 'ChatGPT'
    program = 'codex'
    install_hint = 'Install the Codex CLI: npm install -g @openai/codex'
    login_hint = 'Open a terminal, run "codex login" and sign in with your ChatGPT account.'
    remembers = False
    tasks_unsupported = ("can only chat for now: Codex's own shell can't be switched off, "
                         'so it could read files you did not give it')

    def status(self):
        if not self.executable():
            return AgentStatus(False, False, False, 'Codex CLI is not installed', self.install_hint)
        code, out = self._quick([self.executable(), 'login', 'status'])
        if code == 0:
            return AgentStatus(True, True, True, out.strip().splitlines()[0] if out.strip()
                               else 'Logged in to Codex')
        if code is None:
            return AgentStatus(True, True, None, 'Codex CLI is installed')
        return AgentStatus(False, True, False, 'Codex is not logged in', self.login_hint)

    def command(self, prompt, system):
        fd, self._answer_file = tempfile.mkstemp(prefix='answer-', suffix='.txt',
                                                 dir=self.workdir)
        os.close(fd)
        argv = [self.program, 'exec', '--skip-git-repo-check', '--sandbox', 'read-only',
                '--ephemeral', '--output-last-message', self._answer_file]
        if self.model:
            argv += ['--model', self.model]
        argv.append(f'{system}\n\n{prompt}')
        return argv

    def parse(self, stdout, stderr, returncode):
        try:
            with open(self._answer_file, encoding='utf-8') as f:
                text = f.read().strip()
        except OSError:
            text = ''
        finally:
            try:
                os.unlink(self._answer_file)
            except OSError:
                pass
        if returncode != 0 or not text:
            detail = (stderr or stdout).strip().splitlines()[-1:] or ['no output']
            if 'login' in detail[0].lower() or 'auth' in detail[0].lower():
                raise AgentError(f'codex: {detail[0]}',
                                 'I need you to log in to ChatGPT first. Check my settings!')
            raise AgentError(f'codex exited with {returncode}: {detail[0]}')
        return AgentAnswer(text)
