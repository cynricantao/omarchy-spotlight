# AI CLI setup

Open the footer's **AI** selector in All or AI mode, or press **Ctrl+,**. Choose Omarchy default, Hermes, Codex, Claude Code, Gemini CLI, OpenCode, or Custom CLI.

Only the selected CLI is required. Missing executables are marked unavailable; they are never automatically installed. Each CLI handles its own account, model, permissions and workspace-trust prompts. The plugin does not read credentials or change Omarchy's global default.

## Custom CLI

Use a JSON argument array, with exactly one `{prompt}` placeholder after the executable:

```json
["my-ai", "--prompt", "{prompt}"]
```

For a positional prompt:

```json
["my-ai", "--", "{prompt}"]
```

For a value-taking option supporting equals syntax:

```json
["my-ai", "--prompt={prompt}"]
```

Replace `my-ai` with a real executable name or absolute path and use that CLI's documented interactive options. `Save & use` selects it for Spotlight. Quotes, newlines and shell metacharacters in the question remain within the substituted argument; no shell parses the question. Configure credentials through the CLI itself, never in this array.

Custom executables are trusted code. Common direct shell, Python, and Node inline-evaluation forms and environment/privilege-wrapper templates are rejected. This is not a sandbox or a complete interpreter detector. A trusted wrapper file may be used when the CLI needs extra setup; you are responsible for that wrapper's behavior and for choosing a real prompt parameter rather than an executable/script argument.

## Presets

All commands are passed to `omarchy-launch-tui --app-id=org.omarchy.agent` as arrays:

| CLI | Interactive arguments |
|---|---|
| Hermes | `env -u HERMES_SESSION_SOURCE hermes chat --tui --query=<prompt>` |
| Codex | `codex -- <prompt>` |
| Claude Code | `claude -- <prompt>` |
| Gemini CLI | `gemini --prompt-interactive=<prompt>` |
| OpenCode | `opencode --prompt=<prompt>` |

Normal CLI approval settings remain in effect. Startup/login/trust prompts may still require interaction. Old or changed CLI versions may need a custom adapter. Launch planning is tested without paid inference; that is not an authenticated response guarantee.

References: [Claude Code CLI](https://code.claude.com/docs/en/cli-reference), [Gemini CLI](https://geminicli.com/docs/cli/cli-reference/), [OpenCode CLI](https://opencode.ai/docs/cli/), and the installed Hermes/Codex help for the corresponding CLI versions.

## Settings file

`$XDG_CONFIG_HOME/omarchy/spotlight-ai.json` (default `~/.config/omarchy/spotlight-ai.json`). New settings files are private and atomically replaced. Malformed or unsafe files fail closed rather than being overwritten silently.

From an installed plugin directory:

```sh
python3 -B ai_settings.py show
python3 -B ai_settings.py set '{"provider":"codex"}'
python3 -B ai_settings.py set '{"provider":"omarchy"}'
```

These commands change/read local selection only and do not send an AI question.
