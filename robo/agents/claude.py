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
    supports_tasks = True

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

    def task_command(self, prompt, system, mcp_config, max_turns):
        argv = [self.program, '-p', prompt, '--output-format', 'stream-json', '--verbose',
                '--tools', '',                    # none of Claude Code's own tools...
                '--strict-mcp-config', '--mcp-config', mcp_config,
                '--allowedTools', 'mcp__robo',    # ...only Robo's, which run in the sandbox
                '--restricted', '--disable-slash-commands', '--no-session-persistence',
                '--max-turns', str(max_turns), '--system-prompt', system]
        if self.model:
            argv += ['--model', self.model]
        return argv

    def task_event(self, line):
        data = load_json(line)
        if not isinstance(data, dict):
            return None
        kind = data.get('type')
        if kind == 'assistant':
            events = []
            for block in (data.get('message') or {}).get('content') or ():
                if block.get('type') == 'tool_use':
                    events.append({'kind': 'tool', 'name': str(block.get('name', ''))
                                   .replace('mcp__robo__', ''), 'input': block.get('input')})
                elif block.get('type') == 'text' and block.get('text'):
                    events.append({'kind': 'text', 'text': block['text']})
            return events or None
        if kind == 'result':
            ok = not data.get('is_error') and data.get('subtype') == 'success'
            text = str(data.get('result') or data.get('subtype') or '')
            return {'kind': 'result', 'ok': ok, 'text': text}
        if kind == 'system' and data.get('subtype') == 'init':
            bad = [s.get('name') for s in data.get('mcp_servers') or ()
                   if s.get('status') != 'connected']
            if bad:
                return {'kind': 'result', 'ok': False,
                        'text': f'could not start the sandboxed tools ({", ".join(bad)})'}
        return None

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
