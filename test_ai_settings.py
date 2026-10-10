"""Deterministic settings/planner tests; never execute AI programs."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

MODULE_PATH = Path(__file__).with_name("ai_settings.py")
REAL_RUN = subprocess.run
if MODULE_PATH.exists():
    spec = importlib.util.spec_from_file_location("spotlight_ai_settings", MODULE_PATH)
    ai = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ai)
else:
    ai = None


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(ai, "ai_settings.py must implement the settings API")
        scratch = os.environ.get("TMPDIR", tempfile.gettempdir())
        self.temp = tempfile.TemporaryDirectory(prefix="spotlight-ai-test-", dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "config/omarchy/spotlight-ai.json"
        self.installed = {"omarchy", "omarchy-launch-tui", "env", "hermes", "codex"}
        self.default_result = subprocess.CompletedProcess([], 0, "hermes\n", "")
        self.path_patch = patch.object(ai, "config_path", return_value=self.path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.which = patch.object(ai.shutil, "which", side_effect=lambda name: "/bin/" + name if name in self.installed else None).start()
        self.addCleanup(patch.stopall)
        self.run = patch.object(ai.subprocess, "run", return_value=self.default_result).start()

    def write_config(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(value), encoding="utf-8")

    def test_missing_config_shows_inherit_options_without_writing(self):
        self.path_patch.stop()
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "xdg")}):
            self.assertEqual(ai.config_path(), self.root / "xdg/omarchy/spotlight-ai.json")
        with patch.dict(os.environ, {}, clear=True), patch.object(Path, "home", return_value=self.root):
            self.assertEqual(ai.config_path(), self.root / ".config/omarchy/spotlight-ai.json")
        self.path_patch.start()
        state = ai.show()
        self.assertTrue(state["ok"], state)
        self.assertEqual(state["provider"], "omarchy")
        self.assertEqual(state["selected_label"], "Omarchy default (Hermes)")
        self.assertEqual(state["custom_argv"], [])
        self.assertEqual(state["error"], "")
        self.assertEqual(state["config_path"], str(self.path))
        options = {item["id"]: item for item in state["options"]}
        self.assertEqual(list(options), ["omarchy", "hermes", "codex", "claude", "gemini", "opencode", "custom"])
        self.assertTrue(options["codex"]["available"])
        self.assertFalse(options["claude"]["available"])
        self.assertIn("PATH", options["claude"]["reason"])
        self.assertFalse(options["custom"]["available"])
        self.assertIn("configure", options["custom"]["reason"].lower())
        args, kwargs = self.run.call_args
        self.assertEqual(args[0], ["omarchy", "default", "agent"])
        self.assertLessEqual(kwargs["timeout"], 3)
        self.assertFalse(kwargs.get("shell", False))
        self.assertFalse(self.path.exists())
        self.assertFalse(self.path.parent.exists())
        json.dumps(state)

    def test_codex_override_persists_atomically_without_hermes(self):
        self.assertTrue(callable(getattr(ai, "save", None)), "save API required")
        self.assertTrue(callable(getattr(ai, "launch_argv", None)), "launch_argv API required")
        self.installed.remove("hermes")
        state = ai.save({"provider": "codex"})
        self.assertTrue(state["ok"], state)
        self.assertEqual(state["provider"], "codex")
        self.assertEqual(state["selected_label"], "Codex")
        expected = {"version": 1, "provider": "codex", "custom_argv": []}
        self.assertEqual(json.loads(self.path.read_text()), expected)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        original_inode = self.path.stat().st_ino
        with self.path.open("rb") as old_reader:
            self.assertTrue(ai.save({"provider": "codex"})["ok"])
            self.assertEqual(json.loads(old_reader.read()), expected)
            self.assertNotEqual(self.path.stat().st_ino, original_inode)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
        self.assertEqual(ai.show()["provider"], "codex")
        prompt = '--help "quoted"\n$HOME; $(touch never) 🦊'
        default = Mock(side_effect=AssertionError("override must not query global default"))
        self.run.reset_mock()
        self.assertEqual(ai.launch_argv(prompt, default_agent=default),
                         ["omarchy-launch-tui", "--app-id=org.omarchy.agent", "codex", "--", prompt])
        default.assert_not_called()
        self.run.assert_not_called()

    def test_all_presets_use_exact_interactive_literal_argv(self):
        prompt = '--yolo; $(touch "never"); `id`\n$HOME \'quote\' "double" {prompt} 🦊'
        expected = {
            "hermes": ["env", "-u", "HERMES_SESSION_SOURCE", "hermes", "chat", "--tui", "--query=" + prompt],
            "codex": ["codex", "--", prompt],
            "claude": ["claude", "--", prompt],
            "gemini": ["gemini", "--prompt-interactive=" + prompt],
            "opencode": ["opencode", "--prompt=" + prompt],
        }
        self.installed.update(expected)
        default = Mock(side_effect=AssertionError("do not resolve inherited agent"))
        for provider, inner in expected.items():
            with self.subTest(provider=provider):
                self.assertTrue(ai.save({"provider": provider})["ok"])
                self.run.reset_mock()
                argv = ai.launch_argv(prompt, default_agent=default)
                self.assertEqual(argv, ["omarchy-launch-tui", "--app-id=org.omarchy.agent"] + inner)
                self.assertFalse({"--yolo", "--auto", "--approve-for-me", "--dangerously-skip-permissions", "--dangerously-bypass-approvals-and-sandbox", "--full-auto"}.intersection(argv))
                self.run.assert_not_called()
        default.assert_not_called()

    def test_inherit_resolves_each_launch_without_fallback(self):
        default = Mock(side_effect=["hermes", "codex"])
        try:
            first = ai.launch_argv("first", default_agent=default)
        except KeyError:
            self.fail("inherit must resolve the supplied default_agent callable")
        self.assertEqual(first[2:], ["env", "-u", "HERMES_SESSION_SOURCE", "hermes", "chat", "--tui", "--query=first"])
        self.assertEqual(ai.launch_argv("second", default_agent=default)[2:], ["codex", "--", "second"])
        self.assertEqual(default.call_count, 2)
        self.run.assert_not_called()
        self.assertEqual(ai.launch_argv("read default")[2:6], ["env", "-u", "HERMES_SESSION_SOURCE", "hermes"])
        for selected in (None, "", "unsupported", "Hermes", " codex ", []):
            with self.subTest(selected=selected):
                with self.assertRaisesRegex(ValueError, "default|unsupported"):
                    ai.launch_argv("private prompt", default_agent=lambda: selected)
        self.default_result.stdout = "unknown\n"
        state = ai.save({"provider": "omarchy"})
        self.assertTrue(state["ok"], state)
        self.assertIn("unsupported", state["error"])
        self.assertFalse(state["options"][0]["available"])
        self.assertEqual(json.loads(self.path.read_text())["provider"], "omarchy")
        self.run.side_effect = subprocess.TimeoutExpired("omarchy", 3)
        state = ai.show()
        self.assertIn("Could not read", state["error"])
        with self.assertRaisesRegex(ValueError, "Could not read"):
            ai.launch_argv("private prompt")

    def test_missing_dependencies_refuse_selection_without_mutation(self):
        state = ai.save({"provider": "claude"})
        self.assertFalse(state["ok"], "missing preset must not be persisted")
        self.assertIn("PATH", state["error"])
        self.assertFalse(self.path.exists())
        self.assertTrue(ai.save({"provider": "codex"})["ok"])
        previous = self.path.read_bytes()
        for executable in ("codex", "omarchy-launch-tui"):
            with self.subTest(executable=executable):
                self.installed.remove(executable)
                state = ai.save({"provider": "codex"})
                self.assertFalse(state["ok"], state)
                self.assertIn(executable.lower(), state["error"].lower())
                self.assertEqual(self.path.read_bytes(), previous)
                with self.assertRaisesRegex(ValueError, "PATH"):
                    ai.launch_argv("do not emit this")
                self.installed.add(executable)
        self.installed.remove("env")
        self.assertFalse(ai.save({"provider": "hermes"})["ok"])
        with self.assertRaisesRegex(ValueError, "env"):
            self.write_config({"version": 1, "provider": "omarchy", "custom_argv": []})
            ai.launch_argv("question", default_agent=lambda: "hermes")
        self.installed.remove("omarchy")
        state = ai.save({"provider": "omarchy"})
        self.assertTrue(state["ok"], state)
        self.assertIn("Omarchy", state["error"])
        with self.assertRaisesRegex(ValueError, "Omarchy"):
            ai.launch_argv("question")

    def test_invalid_settings_are_fail_closed_and_never_overwritten(self):
        valid = {"version": 1, "provider": "codex", "custom_argv": []}
        bad_values = [
            "not-json SECRET", "[]", "null", "{" ,
            json.dumps({**valid, "version": 2}),
            json.dumps({**valid, "version": True}),
            json.dumps({**valid, "provider": "SECRET"}),
            json.dumps({**valid, "custom_argv": "SECRET"}),
            json.dumps({**valid, "custom_argv": [3]}),
            json.dumps({**valid, "token": "SECRET"}),
            '{"version":1,"version":2,"provider":"codex","custom_argv":[]}',
            " " * 65537,
        ]
        self.path.parent.mkdir(parents=True)
        for raw in bad_values:
            with self.subTest(case=bad_values.index(raw)):
                self.path.write_text(raw)
                try:
                    shown = ai.show()
                except (ValueError, TypeError, KeyError):
                    self.fail("show must return a sanitized structured settings error")
                self.assertFalse(shown["ok"])
                self.assertNotIn("SECRET", json.dumps(shown))
                saved = ai.save({"provider": "hermes"})
                self.assertFalse(saved["ok"])
                self.assertEqual(self.path.read_text(), raw)
                with self.assertRaises(ValueError):
                    ai.launch_argv("private question")
        self.path.unlink()
        target = self.root / "secret-target"
        target.write_text("SECRET")
        self.path.symlink_to(target)
        for operation in (ai.show, lambda: ai.save({"provider": "codex"})):
            state = operation()
            self.assertFalse(state["ok"])
            self.assertIn("symlink", state["error"].lower())
            self.assertNotIn("SECRET", json.dumps(state))
        with self.assertRaises(ValueError):
            ai.launch_argv("private question")
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(target.read_text(), "SECRET")
        self.path.unlink()
        os.mkfifo(self.path)
        self.assertFalse(ai.show()["ok"])
        self.assertFalse(ai.save({"provider": "codex"})["ok"])
        self.assertTrue(stat.S_ISFIFO(self.path.stat().st_mode))

    def test_invalid_save_payload_never_mutates_previous_settings(self):
        self.assertTrue(ai.save({"provider": "codex"})["ok"])
        previous = self.path.read_bytes()
        payloads = [
            {"provider": "codex", "credentials": "SECRET"},
            {"version": 2}, {"provider": []}, {"provider": "unknown"},
            {"custom_argv": "bad"}, {"custom_argv": [3]},
            {"custom_argv": ["x" * 65537, "{prompt}"]}, None, [], "bad",
        ]
        for index, payload in enumerate(payloads):
            with self.subTest(index=index):
                result = ai.save(payload)
                self.assertFalse(result["ok"], "invalid settings payload must be rejected")
                self.assertNotIn("SECRET", json.dumps(result))
                self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_custom_template_is_literal_and_survives_provider_switches(self):
        self.installed.add("trusted-agent")
        marker = self.root / "MUST_NOT_EXIST"
        prompt = f'--help $(touch "{marker}"); $HOME\n"quotes" {{prompt}}'
        for template in (["trusted-agent", "--", "{prompt}"],
                         ["trusted-agent", "", "{literal}", "--prompt={prompt}"]):
            with self.subTest(template=template):
                state = ai.save({"provider": "custom", "custom_argv": template})
                self.assertTrue(state["ok"], state)
                self.assertEqual(state["selected_label"], "Custom")
                self.assertTrue(state["options"][-1]["available"])
                self.assertEqual(state["error"], "")
                self.assertEqual(state["custom_argv"], template)
                self.assertEqual(json.loads(self.path.read_text())["custom_argv"], template)
                default = Mock(side_effect=AssertionError("no default resolution"))
                self.run.reset_mock()
                self.assertEqual(ai.launch_argv(prompt, default_agent=default),
                                 ["omarchy-launch-tui", "--app-id=org.omarchy.agent"] + [arg.replace("{prompt}", prompt) for arg in template])
                self.run.assert_not_called()
                self.assertFalse(marker.exists())
                self.assertTrue(ai.save({"provider": "codex"})["ok"])
                self.assertEqual(ai.show()["custom_argv"], template)
                self.assertTrue(ai.save({"provider": "custom"})["ok"])
        self.installed.remove("trusted-agent")
        self.assertFalse(ai.show()["options"][-1]["available"])
        previous = self.path.read_bytes()
        state = ai.save({"provider": "custom"})
        self.assertFalse(state["ok"])
        self.assertIn("PATH", state["error"])
        self.assertEqual(self.path.read_bytes(), previous)
        with self.assertRaisesRegex(ValueError, "PATH"):
            ai.launch_argv("question")

    def test_custom_templates_reject_invalid_or_inline_evaluation(self):
        self.installed.update({"trusted-agent", "bash", "sh", "zsh", "fish", "python3", "node", "/bin/bash"})
        self.assertTrue(ai.save({"provider": "codex"})["ok"])
        previous = self.path.read_bytes()
        templates = [
            [], ["trusted-agent"], ["trusted-agent", "no placeholder"],
            ["trusted-agent", "{prompt}", "{prompt}"],
            ["trusted-agent", "{prompt}{prompt}"], ["{prompt}", "arg"],
            ["", "{prompt}"], [" ", "{prompt}"], ["trusted-agent", "{prompt}\x00"],
            ["bash", "-c", "{prompt}"], ["sh", "-c", "echo {prompt}"],
            ["zsh", "-lc", "{prompt}"], ["fish", "--command", "{prompt}"],
            ["/bin/bash", "-xc", "{prompt}"], ["python3", "-c", "{prompt}"],
            ["node", "-e", "{prompt}"], ["node", "--eval={prompt}"],
        ]
        for index, template in enumerate(templates):
            with self.subTest(index=index):
                state = ai.save({"provider": "custom", "custom_argv": template})
                self.assertFalse(state["ok"], "unsafe custom template accepted")
                self.assertEqual(self.path.read_bytes(), previous)
                self.write_config({"version": 1, "provider": "custom", "custom_argv": template})
                with self.assertRaises(ValueError):
                    ai.launch_argv("untrusted prompt")
                self.path.write_bytes(previous)
        self.assertFalse(ai.save({"provider": "codex", "custom_argv": ["trusted-agent", "missing"]})["ok"])
        self.assertEqual(self.path.read_bytes(), previous)

    def test_prompt_is_bounded_before_any_dependency_resolution(self):
        default = Mock(side_effect=AssertionError("invalid prompt must not resolve provider"))
        for prompt in (None, 7, "nul\x00SECRET", "x" * 32769, "🦊" * 8193, "\ud800"):
            with self.subTest(kind=type(prompt).__name__):
                with self.assertRaisesRegex(ValueError, "prompt|Prompt") as raised:
                    ai.launch_argv(prompt, default_agent=default)
                self.assertNotIn("SECRET", str(raised.exception))
        default.assert_not_called()
        self.run.assert_not_called()
        self.assertTrue(ai.save({"provider": "codex"})["ok"])
        for prompt in ("", " \n ", "x" * 32768):
            self.assertEqual(ai.launch_argv(prompt)[-1], prompt)


    def test_cli_emits_one_json_object_and_reads_back_saved_state(self):
        env = {**os.environ, "XDG_CONFIG_HOME": str(self.root / "cli-config"), "PATH": ""}
        path = self.root / "cli-config/omarchy/spotlight-ai.json"

        def invoke(*args):
            result = REAL_RUN([sys.executable, "-B", str(MODULE_PATH), *args],
                              env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.stderr, "")
            self.assertEqual(len(result.stdout.splitlines()), 1, "CLI must emit exactly one JSON object")
            return result, json.loads(result.stdout)

        result, state = invoke("show")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(state["ok"])
        self.assertEqual(state["provider"], "omarchy")
        self.assertFalse(path.exists())
        result, state = invoke("set", '{"provider":"omarchy"}')
        self.assertEqual(result.returncode, 0)
        self.assertTrue(state["ok"])
        self.assertIn("PATH", state["error"])
        self.assertEqual(json.loads(path.read_text()), {"version": 1, "provider": "omarchy", "custom_argv": []})
        self.assertEqual(invoke("show")[1], state)
        previous = path.read_bytes()
        for args in (("set", "SECRET"), ("set", "null"), ("set", " " * 65537),
                     ("set", '{"provider":"codex","provider":"omarchy"}'),
                     ("set", '{"provider":"codex"}'), ("show", "SECRET"), (), ("unknown",)):
            with self.subTest(args_count=len(args)):
                result, state = invoke(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(state["ok"])
                self.assertNotIn("SECRET", result.stdout)
                self.assertEqual(path.read_bytes(), previous)

    def test_atomic_publication_handles_replacement_failures_privately(self):
        self.path.parent.mkdir(parents=True)
        previous_umask = os.umask(0o777)
        try:
            self.assertTrue(ai.save({"provider": "codex"})["ok"])
        finally:
            os.umask(previous_umask)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        previous = self.path.read_bytes()
        target = self.root / "untouched-target"
        target.write_text("SECRET")
        for replacement in ("directory", "symlink"):
            with self.subTest(replacement=replacement):
                changed = False

                def resolve(name):
                    nonlocal changed
                    if name == "hermes" and not changed:
                        changed = True
                        self.path.unlink()
                        if replacement == "directory":
                            self.path.mkdir()
                        else:
                            self.path.symlink_to(target)
                    return "/bin/" + name if name in self.installed else None

                self.which.side_effect = resolve
                try:
                    state = ai.save({"provider": "hermes"})
                except OSError:
                    self.fail("filesystem publication failures need structured sanitized errors")
                self.assertFalse(state["ok"])
                self.assertNotIn("SECRET", json.dumps(state))
                self.assertEqual(list(self.path.parent.iterdir()), [self.path])
                if replacement == "directory":
                    self.assertTrue(self.path.is_dir())
                    self.path.rmdir()
                else:
                    self.assertTrue(self.path.is_symlink())
                    self.path.unlink()
                self.assertEqual(target.read_text(), "SECRET")
                self.path.write_bytes(previous)


if __name__ == "__main__":
    unittest.main()
