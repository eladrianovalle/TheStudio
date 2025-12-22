from unittest import mock

import pytest

from studio.iteration import run_iterative_kickoff, _safe_max_iterations


class CrewFactory:
    """Test helper that yields scripted outputs for each kickoff invocation."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def __call__(self):
        factory = self

        class _Crew:
            def kickoff(self, inputs):
                response = factory._responses[factory.calls]
                factory.calls += 1
                return response

        return _Crew()


def test_iterates_until_approved_before_cap():
    responses = [
        "Some critique...\nVERDICT: REJECTED",
        "Improved plan!\nVERDICT: APPROVED",
    ]
    factory = CrewFactory(responses)
    
    with mock.patch("studio.iteration._run_implementation_phase", return_value=None):
        result = run_iterative_kickoff(
            crew_factory=factory,
            phase="market",
            base_inputs={"game_idea": "Test"},
            max_iterations=5,
        )

    assert result["verdict"] == "APPROVED"
    assert result["iterations_run"] == 2
    assert result["accepted"] is True
    assert result["limit_reached"] is False


def test_respects_iteration_cap_and_flags_limit():
    responses = [
        "Still bad.\nVERDICT: REJECTED",
        "Nope.\nVERDICT: REJECTED",
    ]
    factory = CrewFactory(responses)
    result = run_iterative_kickoff(
        crew_factory=factory,
        phase="design",
        base_inputs={"game_idea": "Test"},
        max_iterations=2,
    )

    assert result["verdict"] == "REJECTED"
    assert result["iterations_run"] == 2
    assert result["accepted"] is False
    assert result["limit_reached"] is True


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, 3),
        ("", 3),
        ("0", 3),
        ("-1", 3),
        ("5", 5),
        (10, 10),
    ],
)
def test_safe_max_iterations_defaults_to_three(raw, expected):
    assert _safe_max_iterations(raw) == expected


def test_implementation_phase_runs_after_approval():
    """Test that implementation phase runs after approval and adds to history."""
    responses = [
        "Great idea!\nVERDICT: APPROVED",
    ]
    factory = CrewFactory(responses)
    
    mock_impl_result = "## Market Implementation\n\n1. Target Audience: Gamers aged 18-35\n2. Competitors: Game A, Game B"
    
    with mock.patch("studio.iteration._run_implementation_phase", return_value=mock_impl_result):
        result = run_iterative_kickoff(
            crew_factory=factory,
            phase="market",
            base_inputs={"game_idea": "Test"},
            max_iterations=5,
        )
    
    assert result["accepted"] is True
    assert result["iterations_run"] == 2  # 1 approval + 1 implementation
    assert result["verdict"] == "IMPLEMENTATION"
    assert len(result["history"]) == 2
    assert result["history"][0]["verdict"] == "APPROVED"
    assert result["history"][1]["verdict"] == "IMPLEMENTATION"
    assert mock_impl_result in result["result"]


def test_feedback_loop_passes_rejection_to_advocate():
    """Test that rejection feedback is passed to the next iteration."""
    responses = [
        "Fatal flaw: No monetization.\nVERDICT: REJECTED",
        "Added monetization!\nVERDICT: APPROVED",
    ]
    factory = CrewFactory(responses)
    
    with mock.patch("studio.iteration._run_implementation_phase", return_value=None):
        result = run_iterative_kickoff(
            crew_factory=factory,
            phase="design",
            base_inputs={"game_idea": "Test"},
            max_iterations=5,
        )
    
    assert result["accepted"] is True
    assert result["iterations_run"] == 2
    assert len(result["history"]) == 2
    
    # Verify the first iteration was rejected
    assert result["history"][0]["verdict"] == "REJECTED"
    assert "Fatal flaw" in result["history"][0]["result"]
    
    # Verify the second iteration was approved
    assert result["history"][1]["verdict"] == "APPROVED"
