"""Gemini, through Google's Gemini CLI (`gemini -p`).

Log in once by running `gemini` and choosing "Login with Google"; Robo uses
that login (cached in ~/.gemini). Runs in Robo's own empty folder.

Written from the Gemini CLI documentation; not yet tried against a real
installation (it wasn't installed where this was built).
"""
import os

from .base import AgentAnswer, AgentBackend, AgentError, AgentStatus, load_json


class GeminiCli(AgentBackend):
    id = 'gemini'
    name = 'Gemini'
    program = 'gemini'
    install_hint = 'Install the Gemini CLI: npm install -g @google/gemini-cli'
    login_hint = 'Open a terminal, run "gemini" and choose Login with Google.'
    remembers = False
    tasks_unsupported = ("can only chat for now: Gemini CLI's own tools can't be fully "
                         'switched off yet, so it could read files you did not give it')

    def status(self):
        if not self.executable():
            return AgentStatus(False, False, False, 'Gemini CLI is not installed',
                               self.install_hint)
        home = os.path.expanduser('~/.gemini')
        if os.path.exists(os.path.join(home, 'oauth_creds.json')):
            return AgentStatus(True, True, True, 'Logged in to Gemini with Google')
        return AgentStatus(True, True, None, 'Gemini CLI is installed (log in once in a terminal)',
                           self.login_hint)

    def command(self, prompt, system):
        argv = [self.program, '-p', f'{system}\n\n{prompt}', '--output-format', 'json']
        if self.model:
            argv += ['--model', self.model]
        return argv

    def parse(self, stdout, stderr, returncode):
        data = load_json(stdout)
        if isinstance(data, dict) and data.get('error'):
            err = data['error'] if isinstance(data['error'], dict) else {'message': data['error']}
            if err.get('type') == 'AuthError':
                raise AgentError(f'gemini: {err.get("message")}',
                                 'I need you to log in to Gemini first. Check my settings!')
            raise AgentError(f'gemini: {err.get("message")}')
        if isinstance(data, dict) and data.get('response'):
            return AgentAnswer(str(data['response']).strip())
        text = stdout.strip()
        if returncode == 0 and text and data is None:    # older CLI: plain text output
            return AgentAnswer(text)
        detail = (stderr or stdout).strip().splitlines()[-1:] or ['no output']
        raise AgentError(f'gemini exited with {returncode}: {detail[0]}')
