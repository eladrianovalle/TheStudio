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

    def test_setup_cfg_section_turns_the_gate_on(self):
        (self.root / "setup.cfg").write_text(
            "[mutmut]\npaths_to_mutate=studio/\n", encoding="utf-8"
        )
        profile = impl_loop.resolve_profile(self.root)
        self.assertTrue(profile.require_mutation_check)
        self.assertEqual(profile.mutation_note, "")

    def test_pyproject_section_turns_the_gate_on(self):
        (self.root / "pyproject.toml").write_text(
            '[tool.mutmut]\npaths_to_mutate = ["src/"]\n', encoding="utf-8"
        )
        self.assertTrue(impl_loop.resolve_profile(self.root).require_mutation_check)

    def test_a_mutmut_config_module_turns_the_gate_on(self):
        (self.root / "mutmut_config.py").write_text("def pre_mutation(context):\n    pass\n", encoding="utf-8")
        self.assertTrue(impl_loop.resolve_profile(self.root).require_mutation_check)

    def test_a_pyproject_without_a_mutmut_section_does_not(self):
        """The marker is the section, not the file — pyproject.toml is in every Python repo."""
        (self.root / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        self.assertFalse(impl_loop.resolve_profile(self.root).require_mutation_check)

    def test_an_unreadable_config_file_does_not_turn_the_gate_on(self):
        """Refusing to guess: unreadable is not the same as configured."""
        (self.root / "setup.cfg").write_bytes(b"\xff\xfe[mutmut]\x00")
        self.assertFalse(impl_loop.resolve_profile(self.root).require_mutation_check)

    def test_studio_itself_still_gets_the_gate(self):
        """This repo has a scoped [mutmut] in studio/setup.cfg, so nothing regresses here."""
        studio_root = Path(__file__).resolve().parent.parent
        self.assertTrue(impl_loop.resolve_profile(studio_root).require_mutation_check)


if __name__ == "__main__":
    unittest.main()
