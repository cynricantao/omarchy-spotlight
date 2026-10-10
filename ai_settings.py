"""Spotlight-local AI selection and literal argv planning (Python stdlib only).

This module never launches an AI or changes Omarchy's global default. Availability
means executable presence, not authentication or a tested provider connection.
Custom commands are trusted local programs, not sandboxed or proven AI clients.
Store no credentials in argv: use the CLI's own account configuration. Only the
literal {prompt} token is substituted; all other braces/arguments are unchanged.
"""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import safe_storage

LABELS = {
    "omarchy": "Omarchy default", "hermes": "Hermes", "codex": "Codex",
    "claude": "Claude Code", "gemini": "Gemini CLI", "opencode": "OpenCode",
    "custom": "Custom",
}
PRESETS = ("hermes", "codex", "claude", "gemini", "opencode")
MAX_CONFIG_BYTES = 65536
MAX_PROMPT_BYTES = 32768


def _empty_config():
    return {"version": 1, "provider": "omarchy", "custom_argv": []}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Settings JSON contains duplicate fields.")
        result[key] = value
    return result


def _validate_config(config):
    if not isinstance(config, dict) or set(config) != {"version", "provider", "custom_argv"}:
        raise ValueError("Settings must contain only version, provider and custom_argv; never store credentials here.")
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Unsupported settings version; version 1 is required.")
    if not isinstance(config["provider"], str) or config["provider"] not in LABELS:
        raise ValueError("Unknown provider; choose a listed Spotlight provider.")
    argv = config["custom_argv"]
    if not isinstance(argv, list) or any(not isinstance(arg, str) for arg in argv):
        raise ValueError("custom_argv must be a JSON array of strings.")
    if len(json.dumps(config, ensure_ascii=True).encode("ascii")) + 1 > MAX_CONFIG_BYTES:
        raise ValueError("Settings exceed the 64 KiB size limit.")
    if argv:
        _validate_custom(argv)
    return config


def _validate_custom(argv):
    if len(argv) < 2 or not argv[0].strip() or "{prompt}" in argv[0]:
        raise ValueError("Custom argv needs an executable and one {prompt} argument after it.")
    if any("\x00" in arg for arg in argv):
        raise ValueError("Custom argv cannot contain NUL characters.")
    if sum(arg.count("{prompt}") for arg in argv[1:]) != 1:
        raise ValueError("Custom argv must contain exactly one {prompt} placeholder after the executable.")
    executable = Path(argv[0]).name
    if executable in {"env", "sudo", "doas", "su", "xargs"}:
        raise ValueError("Use the AI executable directly, not an environment/privilege wrapper.")
    shells = {"sh", "bash", "dash", "zsh", "fish", "ksh", "csh", "tcsh"}
    python = re.fullmatch(r"(?:python|pypy)[0-9.]*", executable)
    for arg in argv[1:]:
        if arg == "--":
            break
        short = arg.startswith("-") and not arg.startswith("--")
        if ((executable in shells or python) and
                ((short and "c" in arg[1:]) or arg.split("=", 1)[0] == "--command")):
            raise ValueError("Inline shell/interpreter evaluation is unsafe; use a trusted wrapper executable.")
        if executable in {"node", "nodejs"} and (
                (short and any(flag in arg[1:] for flag in "ep")) or
                arg.split("=", 1)[0] in {"--eval", "--print"}):
            raise ValueError("Inline shell/interpreter evaluation is unsafe; use a trusted wrapper executable.")


def config_path():
    """Return the Spotlight-only settings path; do not create it."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "omarchy/spotlight-ai.json"


def _default_agent():
    if not shutil.which("omarchy"):
        raise ValueError("Omarchy is not on PATH; choose an installed provider in Spotlight settings.")
    try:
        result = subprocess.run(["omarchy", "default", "agent"], capture_output=True,
                                text=True, timeout=3, check=False)
    except (OSError, subprocess.SubprocessError):
        raise ValueError("Could not read the Omarchy default agent; choose a provider in Spotlight settings.") from None
    if result.returncode or not result.stdout.strip():
        raise ValueError("Omarchy has no readable default agent; configure its default or select a provider.")
    return result.stdout.strip()


def _preset_reason(provider):
    if provider not in PRESETS:
        return "Omarchy default is unsupported; select Hermes, Codex, Claude Code, Gemini CLI or OpenCode."
    if not shutil.which(provider):
        return f"{LABELS[provider]} is not on PATH; install it or choose another provider."
    for dependency in (["env"] if provider == "hermes" else []) + ["omarchy-launch-tui"]:
        if not shutil.which(dependency):
            return f"Required executable {dependency} is not on PATH; repair the installation."
    return ""


def _read_config():
    safe_storage.check_parents(config_path())
    try:
        fd = os.open(config_path(), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return _empty_config()
    except OSError:
        raise ValueError("Cannot read settings; refuse symlink files and check access permissions.") from None
    try:
        with os.fdopen(fd, "rb") as stream:
            info = safe_storage.validate_fd(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Settings must be a regular file, not a symlink or special file.")
            if info.st_size > MAX_CONFIG_BYTES:
                raise ValueError("Settings exceed the 64 KiB size limit.")
            raw = stream.read(MAX_CONFIG_BYTES + 1)
        if len(raw) > MAX_CONFIG_BYTES:
            raise ValueError("Settings exceed the 64 KiB size limit.")
        try:
            config = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        except (ValueError, RecursionError):
            raise ValueError("Settings contain invalid JSON; repair the file before saving.") from None
        return _validate_config(config)
    except OSError:
        raise ValueError("Cannot read settings; check file access permissions.") from None


def _custom_reason(argv):
    if not argv:
        return "Configure a trusted custom CLI argv template first."
    if not shutil.which(argv[0]):
        return "Custom executable is not on PATH; install it or specify its executable path."
    if not shutil.which("omarchy-launch-tui"):
        return "Required executable omarchy-launch-tui is not on PATH; repair the installation."
    return ""


def show():
    """Return JSON-serializable selection, availability and diagnostic metadata."""
    config_error = ""
    try:
        config = _read_config()
    except ValueError as exc:
        config, config_error = _empty_config(), str(exc)
    provider = config["provider"]
    try:
        inherited = _default_agent()
        reason = _preset_reason(inherited)
    except ValueError as exc:
        inherited, reason = None, str(exc)
    selected_label = LABELS["omarchy"]
    if inherited in PRESETS:
        selected_label += f" ({LABELS[inherited]})"
    options = [{"id": "omarchy", "label": selected_label,
                "available": not reason, "reason": reason}]
    for preset in PRESETS:
        why = _preset_reason(preset)
        options.append({"id": preset, "label": LABELS[preset],
                        "available": not why, "reason": why})
    custom_reason = _custom_reason(config["custom_argv"])
    options.append({"id": "custom", "label": "Custom", "available": not custom_reason,
                    "reason": custom_reason})
    chosen = next(item for item in options if item["id"] == provider)
    return {"ok": not config_error, "provider": provider, "selected_label": chosen["label"],
            "options": options, "custom_argv": config["custom_argv"], "error": config_error or chosen["reason"],
            "config_path": str(config_path())}


def save(payload):
    """Merge the local provider/custom argv fields and atomically persist them."""
    try:
        config = _read_config()
        if not isinstance(payload, dict) or set(payload) - {"provider", "custom_argv"}:
            raise ValueError("Only provider and custom_argv may be saved; never store credentials here.")
        config.update(payload)
        _validate_config(config)
    except ValueError as exc:
        state = show()
        state.update(ok=False, error=str(exc))
        return state
    if config["provider"] != "omarchy":
        reason = (_custom_reason(config["custom_argv"]) if config["provider"] == "custom"
                  else _preset_reason(config["provider"]))
        if reason:
            state = show()
            state.update(ok=False, error=reason)
            return state
    path = config_path()
    name = None
    try:
        safe_storage.require_directory(path.parent, create=True)
        fd, name = tempfile.mkstemp(prefix=".spotlight-ai-", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(config, stream, ensure_ascii=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Recheck after dependency resolution; replacement never follows links.
        try:
            target_mode = path.lstat().st_mode
        except FileNotFoundError:
            target_mode = None
        if target_mode is not None and not stat.S_ISREG(target_mode):
            raise ValueError("Refusing to replace a symlink or special settings file.")
        os.replace(name, path)
    except (OSError, ValueError):
        state = show()
        state.update(ok=False, error="Cannot save settings; check permissions and remove any symlink or special file at the settings path.")
        return state
    finally:
        if name is not None:
            try:
                os.unlink(name)
            except FileNotFoundError:
                pass
    return show()


def launch_argv(prompt, default_agent=None):
    """Plan a normal-approval terminal launch; never execute the returned argv."""
    if not isinstance(prompt, str) or "\x00" in prompt:
        raise ValueError("Prompt must be a string without NUL characters.")
    try:
        prompt_size = len(prompt.encode("utf-8"))
    except UnicodeError:
        raise ValueError("Prompt must be valid UTF-8 text.") from None
    if prompt_size > MAX_PROMPT_BYTES:
        raise ValueError("Prompt exceeds the 32 KiB UTF-8 limit; shorten the question.")
    config = _read_config()
    provider = config["provider"]
    if provider == "custom":
        reason = _custom_reason(config["custom_argv"])
        if reason:
            raise ValueError(reason)
        return ["omarchy-launch-tui", "--app-id=org.omarchy.agent"] + [
            arg.replace("{prompt}", prompt) for arg in config["custom_argv"]]
    if provider == "omarchy":
        provider = (_default_agent if default_agent is None else default_agent)()
    reason = _preset_reason(provider)
    if reason:
        raise ValueError(reason)
    inner = {
        "hermes": ["env", "-u", "HERMES_SESSION_SOURCE", "hermes", "chat", "--tui", "--query=" + prompt],
        "codex": ["codex", "--", prompt],
        "claude": ["claude", "--", prompt],
        "gemini": ["gemini", "--prompt-interactive=" + prompt],
        "opencode": ["opencode", "--prompt=" + prompt],
    }[provider]
    return ["omarchy-launch-tui", "--app-id=org.omarchy.agent"] + inner


def _main(args):
    try:
        if args == ["show"]:
            result = show()
        elif len(args) == 2 and args[0] == "set":
            if len(args[1].encode("utf-8")) > MAX_CONFIG_BYTES:
                raise ValueError("Settings payload exceeds the 64 KiB limit.")
            try:
                payload = json.loads(args[1], object_pairs_hook=_unique_object)
            except (ValueError, RecursionError):
                raise ValueError("Settings payload must be valid JSON with unique fields.") from None
            result = save(payload)
        else:
            raise ValueError("Usage: ai_settings.py show | set '<JSON object>'")
    except (ValueError, OSError):
        # Never expose raw decoder/OS diagnostics, command tokens or user data.
        result = {"ok": False, "error": "Invalid request or inaccessible settings; use show or set with a valid JSON object (64 KiB maximum)."}
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
