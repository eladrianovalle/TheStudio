"""The Python gate profile asks the repository about mutation testing.

`pytest -q` and `ruff check` mean the same thing in every Python repo. `mutmut run`
does not: it takes `paths_to_mutate` from a config section, and given none it guesses a
`src/`, `lib/` or project-named directory. A repo with neither the section nor that
layout gets a gate that errors or mutates the wrong tree on every unit — a failure with
nothing to do with the code being built, which is exactly what stack detection exists to
prevent.

Every install that met the old always-on default turned it off by hand, which is the
measurement behind these tests.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import impl_loop  # noqa: E402
import setup  # noqa: E402


class PythonGateProfileTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # A marker that makes this a Python repo and nothing else.
        (self.root / "conftest.py").write_text("", encoding="utf-8")
        self.addCleanup(self._tmp.cleanup)

    def test_no_mutmut_config_switches_the_gate_off(self):
        profile = impl_loop.resolve_profile(self.root)
        self.assertFalse(
            profile.require_mutation_check,
            "A repo that never told mutmut what to mutate was offered the mutation gate "
            "anyway. That gate cannot pass, and it fails on the unit being built rather "
            "than on the missing config.",
        )
        self.assertEqual(profile.test_command, "pytest -q")
        self.assertEqual(profile.static_checks, ("ruff check {paths}",))

    def test_the_gate_is_off_with_a_note_saying_how_to_turn_it_on(self):
        profile = impl_loop.resolve_profile(self.root)
        self.assertIn("paths_to_mutate", profile.mutation_note)
        self.assertIn("require_mutation_check", profile.mutation_note)

    def test_the_written_config_carries_that_note(self):
        profile = impl_loop.resolve_profile(self.root)
        written = setup._format_loop_toml(profile, self.root)
        self.assertIn("paths_to_mutate", written)
        self.assertIn("require_mutation_check = false", written)

    def test_mutation_command_is_written_even_when_the_gate_is_off(self):
        """So turning the gate on later is one word, not a trip to the documentation."""
        profile = impl_loop.resolve_profile(self.root)
        self.assertEqual(profile.mutation_command, "mutmut run")
        self.assertIn('mutation_command = "mutmut run"', setup._format_loop_toml(profile, self.root))

    def test_setup_cfg_paths_to_mutate_turns_the_gate_on(self):
        (self.root / "setup.cfg").write_text(
            "[mutmut]\npaths_to_mutate=studio/\n", encoding="utf-8"
        )
        profile = impl_loop.resolve_profile(self.root)
        self.assertTrue(profile.require_mutation_check)
        self.assertEqual(profile.mutation_note, "")

    def test_pyproject_paths_to_mutate_turns_the_gate_on(self):
        (self.root / "pyproject.toml").write_text(
            '[tool.mutmut]\npaths_to_mutate = ["src/"]\n', encoding="utf-8"
        )
        self.assertTrue(impl_loop.resolve_profile(self.root).require_mutation_check)

    def test_a_mutmut_section_without_paths_does_not(self):
        """`paths_to_mutate` is the setting that decides what `mutmut run` mutates.

        A section holding only a runner leaves mutmut guessing at a `src/` directory, which
        is the failure this probe exists to prevent.
        """
        (self.root / "setup.cfg").write_text(
            "[mutmut]\nrunner=python -m pytest -q\n", encoding="utf-8"
        )
        self.assertFalse(impl_loop.resolve_profile(self.root).require_mutation_check)

    def test_a_mutmut_config_module_alone_does_not(self):
        """It is mutmut's hook file. It holds pre_mutation/post_mutation and sets no paths."""
        (self.root / "mutmut_config.py").write_text(
            "def pre_mutation(context):\n    pass\n", encoding="utf-8"
        )
        self.assertFalse(impl_loop.resolve_profile(self.root).require_mutation_check)

    def test_the_setting_commented_out_does_not_count(self):
        """Parsed, not substring-matched: a line somebody disabled is not configuration."""
        (self.root / "setup.cfg").write_text(
            "# [mutmut]\n# paths_to_mutate=studio/\n", encoding="utf-8"
        )
        self.assertFalse(impl_loop.resolve_profile(self.root).require_mutation_check)

    def test_the_words_inside_a_pyproject_string_do_not_count(self):
        (self.root / "pyproject.toml").write_text(
            '[project]\nname = "x"\ndescription = "see [tool.mutmut] paths_to_mutate for details"\n',
            encoding="utf-8",
        )
        self.assertFalse(impl_loop.resolve_profile(self.root).require_mutation_check)

    def test_a_pyproject_without_a_mutmut_section_does_not(self):
        """pyproject.toml is in every Python repo; its presence says nothing about mutmut."""
        (self.root / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        self.assertFalse(impl_loop.resolve_profile(self.root).require_mutation_check)

    def test_an_unparsable_config_file_does_not_turn_the_gate_on(self):
        """Refusing to guess: unreadable is not the same as configured."""
        (self.root / "setup.cfg").write_bytes(b"\xff\xfe[mutmut]\x00")
        self.assertFalse(impl_loop.resolve_profile(self.root).require_mutation_check)

    def test_a_malformed_pyproject_does_not_turn_the_gate_on(self):
        (self.root / "pyproject.toml").write_text(
            '[tool.mutmut\npaths_to_mutate = ["src/"]\n', encoding="utf-8"
        )
        self.assertFalse(impl_loop.resolve_profile(self.root).require_mutation_check)

    def test_an_empty_setting_is_not_configuration(self):
        """A key somebody started and did not finish leaves mutmut guessing, same as none."""
        for value in ("", "   "):
            with self.subTest(value=repr(value)):
                (self.root / "setup.cfg").write_text(
                    f"[mutmut]\npaths_to_mutate={value}\n", encoding="utf-8"
                )
                self.assertFalse(impl_loop.resolve_profile(self.root).require_mutation_check)

    def test_an_empty_setting_reads_the_same_in_both_formats(self):
        """The two config files must not disagree about what "empty" means."""
        (self.root / "setup.cfg").unlink(missing_ok=True)
        for value in ('""', "[]", '[" "]'):
            with self.subTest(value=value):
                (self.root / "pyproject.toml").write_text(
                    f"[tool.mutmut]\npaths_to_mutate = {value}\n", encoding="utf-8"
                )
                self.assertFalse(impl_loop.resolve_profile(self.root).require_mutation_check)

    def test_the_probe_looks_where_the_stack_was_detected(self):
        """One root answers both questions, so the two can never point at different trees.

        This repository is the case worth pinning: its Python markers and its mutmut config
        both sit under `studio/`, and its top level has neither. Asked about the top level,
        detection finds no stack at all and the gate question never arises; asked about
        `studio/`, it finds the stack and the config together.
        """
        repo_root = Path(__file__).resolve().parent.parent.parent
        studio_dir = repo_root / "studio"

        self.assertEqual(impl_loop.resolve_profile(repo_root).stacks, ())
        self.assertEqual(impl_loop.resolve_profile(studio_dir).stacks, ("python",))
        self.assertTrue(impl_loop.resolve_profile(studio_dir).require_mutation_check)

    def test_studio_itself_still_gets_the_gate(self):
        """This repo has a scoped [mutmut] in studio/setup.cfg, so nothing regresses here."""
        studio_root = Path(__file__).resolve().parent.parent
        self.assertTrue(impl_loop.resolve_profile(studio_root).require_mutation_check)


if __name__ == "__main__":
    unittest.main()
