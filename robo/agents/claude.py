"""Claude, through Claude Code (`claude -p`).

Log in once with `claude` (then /login) using your Claude Pro or Max account;
Robo uses that login. API-key environment variables are not passed on, so it
is always your subscription that answers.
"""
from .base import AgentAnswer, AgentBackend, AgentError, AgentStatus, load_json


class ClaudeCode(AgentBackend):
    id = 'claude'
    name = 'Claude'
    program = 'claude'
    install_hint = 'Install Claude Code: curl -fsSL https://claude.ai/install.sh | bash'
    login_hint = 'Open a terminal, run "claude" and log in with your Claude account.'
    remembers = True

    def status(self):
        if not self.executable():
            return AgentStatus(False, False, False, 'Claude Code is not installed',
                               self.install_hint)
        code, out = self._quick([self.executable(), 'auth', 'status'])
        info = load_json(out) or {}
        if info.get('loggedIn'):
            plan = info.get('subscriptionType') or info.get('authMethod') or ''
            return AgentStatus(True, True, True,
                               f'Logged in to Claude{f" ({plan})" if plan else ""}')
        if code is None:
            return AgentStatus(True, True, None, 'Claude Code is installed')
        return AgentStatus(False, True, False, 'Claude Code is not logged in', self.login_hint)

    def command(self, prompt, system):
        argv = [self.program, '-p', prompt, '--output-format', 'json',
                '--tools', '',                  # talk only: no files, no commands, no web
                '--restricted', '--strict-mcp-config', '--disable-slash-commands',
                '--effort', 'low',              # chatty answers: quick beats deep
                '--system-prompt', system]
        if self.model:
            argv += ['--model', self.model]
        if self.session:
            argv += ['--resume', self.session]   # remembers the conversation
        return argv

    def parse(self, stdout, stderr, returncode):
        data = load_json(stdout)
        if not isinstance(data, dict):
            detail = (stderr or stdout).strip().splitlines()[-1:] or ['no output']
            if 'login' in (stderr + stdout).lower() or 'auth' in (stderr + stdout).lower():
                raise AgentError(f'claude: {detail[0]}',
                                 'I need you to log in to Claude first. Check my settings!')
            raise AgentError(f'claude exited with {returncode}: {detail[0]}')
        text = str(data.get('result') or '')
        if data.get('is_error') or data.get('subtype', 'success') != 'success':
            low = text.lower()
            if self.session and ('session' in low or 'conversation' in low):
                self.session = None             # an old session vanished: start over
            if 'login' in low or 'auth' in low:
                raise AgentError(f'claude: {text}',
                                 'I need you to log in to Claude first. Check my settings!')
            if 'limit' in low:
                raise AgentError(f'claude: {text}',
                                 "I've used up my Claude messages for now. Let's talk later!")
            raise AgentError(f'claude: {text or data.get("subtype")}')
        return AgentAnswer(text, data.get('session_id'))
