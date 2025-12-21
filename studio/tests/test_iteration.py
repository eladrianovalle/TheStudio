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
