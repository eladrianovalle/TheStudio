"""Tests for clarity score computation, persistence, and formatting.

Tests cover:
  - slugify_topic: normalization, em-dash stripping, edge cases
  - display_name_from_unblocks: extraction of human-readable topic name
  - compute_topic_clarity: score calculation with answer counts and challenge penalty
  - compute_clarity_snapshot: multi-topic grouping, override carry-forward, sorting
  - detect_context_scope: keyword heuristic for broad vs narrow
  - question_density_for_scope: density lookup by scope and score
  - format_clarity_summary: markdown table output with status labels
  - generate_clarity_instructions: agent prompt instructions
  - apply_user_overrides: override application, validation, immutability
  - save/load clarity JSON: round-trip persistence
  - project clarity: .studio/clarity.json convenience functions
"""
import pytest

from decision_points import DecisionPoint
from clarity import (
    TopicClarity,
    ClarityContext,
    ClaritySnapshot,
    slugify_topic,
    display_name_from_unblocks,
    compute_topic_clarity,
    compute_clarity_snapshot,
    detect_context_scope,
    question_density_for_scope,
    format_clarity_summary,
    generate_clarity_instructions,
    apply_user_overrides,
    save_clarity_json,
    load_clarity_json,
    load_project_clarity,
    save_project_clarity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dp(priority="P0", question="Q?", unblocks="Something",
             answer=None, answered_by=None, source_file=None, options=None):
    """Build a DecisionPoint with sensible defaults."""
    return DecisionPoint(
        priority=priority,
        question=question,
        unblocks=unblocks,
        options=options,
        source_file=source_file,
        answer=answer,
        answered_by=answered_by,
    )


# ---------------------------------------------------------------------------
# TopicClarity dataclass
# ---------------------------------------------------------------------------

class TestTopicClarity:
    """Tests for the TopicClarity dataclass."""

    def test_effective_score_uses_score_when_no_override(self):
        tc = TopicClarity(
            topic="core_loop", display_name="Core loop",
            score=0.6, answered_count=3, total_count=5, challenged_count=0,
        )
        assert tc.effective_score == 0.6

    def test_effective_score_uses_override_when_set(self):
        tc = TopicClarity(
            topic="core_loop", display_name="Core loop",
            score=0.6, answered_count=3, total_count=5, challenged_count=0,
            user_override=0.9,
        )
        assert tc.effective_score == 0.9


# ---------------------------------------------------------------------------
# ClaritySnapshot dataclass
# ---------------------------------------------------------------------------

class TestClaritySnapshot:
    """Tests for the ClaritySnapshot dataclass."""

    def test_mean_score_single_topic(self):
        topic = TopicClarity(
            topic="art", display_name="Art", score=0.5,
            answered_count=1, total_count=2, challenged_count=0,
        )
        snap = ClaritySnapshot(
            topics=[topic],
            context=ClarityContext(scope_label="broad", scope_description="High level"),
            created_iso="2026-03-19T00:00:00Z",
        )
        assert snap.mean_score == pytest.approx(0.5)

    def test_mean_score_multiple_topics(self):
        t1 = TopicClarity(
            topic="a", display_name="A", score=0.4,
            answered_count=2, total_count=5, challenged_count=0,
        )
        t2 = TopicClarity(
            topic="b", display_name="B", score=0.8,
            answered_count=4, total_count=5, challenged_count=0,
        )
        snap = ClaritySnapshot(
            topics=[t1, t2],
            context=ClarityContext(scope_label="narrow", scope_description="Detail"),
            created_iso="2026-03-19T00:00:00Z",
        )
        assert snap.mean_score == pytest.approx(0.6)

    def test_mean_score_empty_topics(self):
        snap = ClaritySnapshot(
            topics=[],
            context=ClarityContext(scope_label="broad", scope_description="x"),
            created_iso="2026-03-19T00:00:00Z",
        )
        assert snap.mean_score == 0.0

    def test_get_topic_found(self):
        t = TopicClarity(
            topic="core_loop", display_name="Core loop", score=0.7,
            answered_count=3, total_count=4, challenged_count=0,
        )
        snap = ClaritySnapshot(
            topics=[t],
            context=ClarityContext(scope_label="broad", scope_description="x"),
            created_iso="2026-03-19T00:00:00Z",
        )
        assert snap.get_topic("core_loop") is t

    def test_get_topic_not_found(self):
        snap = ClaritySnapshot(
            topics=[],
            context=ClarityContext(scope_label="broad", scope_description="x"),
            created_iso="2026-03-19T00:00:00Z",
        )
        assert snap.get_topic("missing") is None


# ---------------------------------------------------------------------------
# slugify_topic
# ---------------------------------------------------------------------------

class TestSlugifyTopic:
    """Tests for slugify_topic()."""

    def test_simple_text(self):
        assert slugify_topic("Core loop design") == "core_loop_design"

    def test_em_dash_strips_suffix(self):
        result = slugify_topic("Core loop design — fundamentally different")
        assert result == "core_loop_design"

    def test_en_dash_strips_suffix(self):
        result = slugify_topic("Art pipeline – scheduling concerns")
        assert result == "art_pipeline"

    def test_empty_returns_uncategorized(self):
        assert slugify_topic("") == "uncategorized"

    def test_whitespace_only_returns_uncategorized(self):
        assert slugify_topic("   ") == "uncategorized"

    def test_unicode_text(self):
        result = slugify_topic("Jeu de rôle — stratégie")
        assert result == "jeu_de_rôle"

    def test_multiple_spaces_collapsed(self):
        result = slugify_topic("Core   loop   design")
        assert result == "core_loop_design"


# ---------------------------------------------------------------------------
# display_name_from_unblocks
# ---------------------------------------------------------------------------

class TestDisplayName:
    """Tests for display_name_from_unblocks()."""

    def test_em_dash_extracts_prefix(self):
        result = display_name_from_unblocks(
            "Core loop design — fundamentally different"
        )
        assert result == "Core loop design"

    def test_plain_text(self):
        result = display_name_from_unblocks("Art pipeline scheduling")
        assert result == "Art pipeline scheduling"

    def test_strips_whitespace(self):
        result = display_name_from_unblocks("  Core loop  ")
        assert result.strip() == "Core loop"


# ---------------------------------------------------------------------------
# compute_topic_clarity
# ---------------------------------------------------------------------------

class TestComputeTopicClarity:
    """Tests for compute_topic_clarity()."""

    def test_no_decisions_returns_zero(self):
        tc = compute_topic_clarity("empty", [])
        assert tc.score == 0.0
        assert tc.total_count == 0

    def test_all_answered(self):
        decisions = [
            _make_dp(unblocks="Topic A", answer="Yes", answered_by="user"),
            _make_dp(unblocks="Topic A", answer="No", answered_by="user"),
        ]
        tc = compute_topic_clarity("topic_a", decisions)
        assert tc.score == pytest.approx(1.0)
        assert tc.answered_count == 2
        assert tc.total_count == 2

    def test_none_answered(self):
        decisions = [
            _make_dp(unblocks="Topic A"),
            _make_dp(unblocks="Topic A"),
        ]
        tc = compute_topic_clarity("topic_a", decisions)
        assert tc.score == pytest.approx(0.0)
        assert tc.answered_count == 0

    def test_mixed_answered(self):
        decisions = [
            _make_dp(unblocks="Topic A", answer="Yes", answered_by="user"),
            _make_dp(unblocks="Topic A"),
            _make_dp(unblocks="Topic A"),
            _make_dp(unblocks="Topic A"),
        ]
        tc = compute_topic_clarity("topic_a", decisions)
        assert tc.score == pytest.approx(0.25)
        assert tc.answered_count == 1
        assert tc.total_count == 4

    def test_challenge_penalty_from_contrarian(self):
        """Decisions from contrarian files count as challenged, reducing score."""
        decisions = [
            _make_dp(unblocks="Topic A", answer="Yes", answered_by="user"),
            _make_dp(unblocks="Topic A", answer="Yes", answered_by="user"),
            _make_dp(
                unblocks="Topic A",
                source_file="contrarian--design--01.md",
            ),
        ]
        tc = compute_topic_clarity("topic_a", decisions)
        # 2/3 answered minus 0.1 per challenge = 0.567 exactly.
        # Pin the exact value: a directional `< 0.667` check would survive
        # dropping the penalty (2/3 rounds under 0.667) or scaling it.
        assert tc.challenged_count == 1
        assert tc.score == pytest.approx(2 / 3 - 0.1)

    def test_challenge_penalty_capped_at_zero(self):
        """Score never goes below zero even with many challenges."""
        decisions = [
            _make_dp(unblocks="X", source_file="contrarian--design--01.md"),
            _make_dp(unblocks="X", source_file="contrarian--design--02.md"),
            _make_dp(unblocks="X", source_file="contrarian--design--03.md"),
        ]
        tc = compute_topic_clarity("x", decisions)
        assert tc.score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# compute_clarity_snapshot
# ---------------------------------------------------------------------------

class TestComputeClaritySnapshot:
    """Tests for compute_clarity_snapshot()."""

    def test_empty_decisions(self):
        ctx = ClarityContext(scope_label="broad", scope_description="High level")
        snap = compute_clarity_snapshot([], ctx)
        assert snap.topics == []
        assert snap.mean_score == 0.0

    def test_multiple_topics_grouped(self):
        decisions = [
            _make_dp(unblocks="Core loop design", answer="Yes", answered_by="user"),
            _make_dp(unblocks="Core loop design"),
            _make_dp(unblocks="Art pipeline", answer="Pixel", answered_by="user"),
        ]
        ctx = ClarityContext(scope_label="broad", scope_description="Test")
        snap = compute_clarity_snapshot(decisions, ctx)
        assert len(snap.topics) == 2

    def test_prior_snapshot_carries_override(self):
        """User overrides from a prior snapshot carry forward to matching topics."""
        old_topic = TopicClarity(
            topic="core_loop_design", display_name="Core loop design",
            score=0.5, answered_count=1, total_count=2, challenged_count=0,
            user_override=0.9,
        )
        prior = ClaritySnapshot(
            topics=[old_topic],
            context=ClarityContext(scope_label="broad", scope_description="old"),
            created_iso="2026-03-18T00:00:00Z",
        )
        decisions = [
            _make_dp(unblocks="Core loop design", answer="Yes", answered_by="user"),
            _make_dp(unblocks="Core loop design"),
        ]
        ctx = ClarityContext(scope_label="broad", scope_description="new")
        snap = compute_clarity_snapshot(decisions, ctx, prior_snapshot=prior)

        topic = snap.get_topic("core_loop_design")
        assert topic is not None
        assert topic.user_override == 0.9

    def test_sorted_by_effective_score_ascending(self):
        """Topics are sorted by effective_score ascending (worst first)."""
        decisions = [
            _make_dp(unblocks="TopicA", answer="Yes", answered_by="user"),
            _make_dp(unblocks="TopicB"),
            _make_dp(unblocks="TopicB"),
        ]
        ctx = ClarityContext(scope_label="broad", scope_description="Test")
        snap = compute_clarity_snapshot(decisions, ctx)

        scores = [t.effective_score for t in snap.topics]
        assert scores == sorted(scores)


# ---------------------------------------------------------------------------
# detect_context_scope
# ---------------------------------------------------------------------------

class TestDetectContextScope:
    """Tests for detect_context_scope()."""

    def test_broad_cozy_farming_sim(self):
        ctx = detect_context_scope("A cozy farming sim with social deduction mechanics")
        assert ctx.scope_label == "broad"

    def test_narrow_build_system(self):
        ctx = detect_context_scope("Build the inventory system")
        assert ctx.scope_label == "narrow"

    def test_narrow_module_keyword(self):
        ctx = detect_context_scope("Refactor the lobby module")
        assert ctx.scope_label == "narrow"

    def test_narrow_ui_flow(self):
        ctx = detect_context_scope("lobby UI flow")
        assert ctx.scope_label == "narrow"

    def test_narrow_feature_keyword(self):
        ctx = detect_context_scope("Add the crafting feature")
        assert ctx.scope_label == "narrow"

    def test_broad_generic_concept(self):
        ctx = detect_context_scope("A new battle royale game")
        assert ctx.scope_label == "broad"


# ---------------------------------------------------------------------------
# question_density_for_scope
# ---------------------------------------------------------------------------

class TestQuestionDensityForScope:
    """Tests for question_density_for_scope()."""

    def _tc(self, score):
        """Helper to build a TopicClarity with a given score."""
        return TopicClarity(
            topic="t", display_name="T", score=score,
            answered_count=0, total_count=1, challenged_count=0,
        )

    # Alignment scope: high unless >= 0.8
    def test_alignment_low_score_high_density(self):
        assert question_density_for_scope("alignment", self._tc(0.3)) == "high"

    def test_alignment_high_score_low_density(self):
        assert question_density_for_scope("alignment", self._tc(0.85)) == "low"

    # Depth scope: high < 0.4, medium < 0.7, low >= 0.7
    def test_depth_low_score(self):
        assert question_density_for_scope("depth", self._tc(0.2)) == "high"

    def test_depth_mid_score(self):
        assert question_density_for_scope("depth", self._tc(0.5)) == "medium"

    def test_depth_high_score(self):
        assert question_density_for_scope("depth", self._tc(0.75)) == "low"

    # Polish scope: low unless < 0.3
    def test_polish_low_score_high_density(self):
        assert question_density_for_scope("polish", self._tc(0.1)) == "high"

    def test_polish_normal_score_low_density(self):
        assert question_density_for_scope("polish", self._tc(0.5)) == "low"

    # Unknown scope defaults to depth behavior
    def test_unknown_scope_defaults_to_depth(self):
        assert question_density_for_scope("unknown_scope", self._tc(0.2)) == "high"
        assert question_density_for_scope("unknown_scope", self._tc(0.5)) == "medium"
        assert question_density_for_scope("unknown_scope", self._tc(0.75)) == "low"


# ---------------------------------------------------------------------------
# format_clarity_summary
# ---------------------------------------------------------------------------

class TestFormatClaritySummary:
    """Tests for format_clarity_summary()."""

    def test_markdown_table_output(self):
        topics = [
            TopicClarity(
                topic="core_loop", display_name="Core loop",
                score=0.9, answered_count=9, total_count=10, challenged_count=0,
            ),
            TopicClarity(
                topic="art", display_name="Art",
                score=0.3, answered_count=3, total_count=10, challenged_count=1,
            ),
        ]
        snap = ClaritySnapshot(
            topics=topics,
            context=ClarityContext(scope_label="broad", scope_description="Test"),
            created_iso="2026-03-19T00:00:00Z",
        )
        result = format_clarity_summary(snap)

        assert "|" in result  # markdown table
        assert "Core loop" in result
        assert "Art" in result

    def test_status_label_settled(self):
        """Score >= 0.8 shows Settled label."""
        topics = [
            TopicClarity(
                topic="x", display_name="X", score=0.85,
                answered_count=8, total_count=10, challenged_count=0,
            ),
        ]
        snap = ClaritySnapshot(
            topics=topics,
            context=ClarityContext(scope_label="broad", scope_description="T"),
            created_iso="2026-03-19T00:00:00Z",
        )
        result = format_clarity_summary(snap)
        assert "Settled" in result

    def test_status_label_settling(self):
        """Score 0.4-0.8 shows Settling label."""
        topics = [
            TopicClarity(
                topic="x", display_name="X", score=0.5,
                answered_count=5, total_count=10, challenged_count=0,
            ),
        ]
        snap = ClaritySnapshot(
            topics=topics,
            context=ClarityContext(scope_label="broad", scope_description="T"),
            created_iso="2026-03-19T00:00:00Z",
        )
        result = format_clarity_summary(snap)
        assert "Settling" in result

    def test_status_label_needs_work(self):
        """Score < 0.4 shows Needs work label."""
        topics = [
            TopicClarity(
                topic="x", display_name="X", score=0.2,
                answered_count=2, total_count=10, challenged_count=0,
            ),
        ]
        snap = ClaritySnapshot(
            topics=topics,
            context=ClarityContext(scope_label="broad", scope_description="T"),
            created_iso="2026-03-19T00:00:00Z",
        )
        result = format_clarity_summary(snap)
        assert "Needs work" in result


# ---------------------------------------------------------------------------
# generate_clarity_instructions
# ---------------------------------------------------------------------------

class TestGenerateClarityInstructions:
    """Tests for generate_clarity_instructions()."""

    def test_settled_topics_listed_as_constraints(self):
        topics = [
            TopicClarity(
                topic="core_loop", display_name="Core loop", score=0.9,
                answered_count=9, total_count=10, challenged_count=0,
            ),
        ]
        snap = ClaritySnapshot(
            topics=topics,
            context=ClarityContext(scope_label="broad", scope_description="T"),
            created_iso="2026-03-19T00:00:00Z",
        )
        result = generate_clarity_instructions(snap, "depth")
        assert "Core loop" in result
        # Settled topics should be referenced as settled/constraint
        lower = result.lower()
        assert "settled" in lower or "constraint" in lower or "established" in lower

    def test_unsettled_topics_listed_for_surfacing(self):
        topics = [
            TopicClarity(
                topic="monetization", display_name="Monetization", score=0.2,
                answered_count=1, total_count=5, challenged_count=0,
            ),
        ]
        snap = ClaritySnapshot(
            topics=topics,
            context=ClarityContext(scope_label="broad", scope_description="T"),
            created_iso="2026-03-19T00:00:00Z",
        )
        result = generate_clarity_instructions(snap, "alignment")
        assert "Monetization" in result

    def test_scope_info_included(self):
        snap = ClaritySnapshot(
            topics=[],
            context=ClarityContext(scope_label="broad", scope_description="High level"),
            created_iso="2026-03-19T00:00:00Z",
        )
        result = generate_clarity_instructions(snap, "alignment")
        # Should mention scope context somehow
        assert len(result) > 0


# ---------------------------------------------------------------------------
# apply_user_overrides
# ---------------------------------------------------------------------------

class TestApplyUserOverrides:
    """Tests for apply_user_overrides()."""

    def test_apply_override(self):
        topics = [
            TopicClarity(
                topic="core_loop", display_name="Core loop", score=0.3,
                answered_count=1, total_count=3, challenged_count=0,
            ),
        ]
        snap = ClaritySnapshot(
            topics=topics,
            context=ClarityContext(scope_label="broad", scope_description="T"),
            created_iso="2026-03-19T00:00:00Z",
        )
        new_snap = apply_user_overrides(snap, {"core_loop": 0.95})

        assert new_snap.get_topic("core_loop").user_override == 0.95
        assert new_snap.get_topic("core_loop").effective_score == 0.95

    def test_does_not_mutate_original(self):
        topics = [
            TopicClarity(
                topic="core_loop", display_name="Core loop", score=0.3,
                answered_count=1, total_count=3, challenged_count=0,
            ),
        ]
        snap = ClaritySnapshot(
            topics=topics,
            context=ClarityContext(scope_label="broad", scope_description="T"),
            created_iso="2026-03-19T00:00:00Z",
        )
        apply_user_overrides(snap, {"core_loop": 0.95})

        # Original must be unchanged
        assert snap.get_topic("core_loop").user_override is None

    def test_invalid_value_raises(self):
        topics = [
            TopicClarity(
                topic="x", display_name="X", score=0.5,
                answered_count=1, total_count=2, challenged_count=0,
            ),
        ]
        snap = ClaritySnapshot(
            topics=topics,
            context=ClarityContext(scope_label="broad", scope_description="T"),
            created_iso="2026-03-19T00:00:00Z",
        )
        with pytest.raises(ValueError):
            apply_user_overrides(snap, {"x": 1.5})

        with pytest.raises(ValueError):
            apply_user_overrides(snap, {"x": -0.1})

    def test_reset_override_with_none(self):
        topics = [
            TopicClarity(
                topic="core_loop", display_name="Core loop", score=0.5,
                answered_count=2, total_count=4, challenged_count=0,
                user_override=0.9,
            ),
        ]
        snap = ClaritySnapshot(
            topics=topics,
            context=ClarityContext(scope_label="broad", scope_description="T"),
            created_iso="2026-03-19T00:00:00Z",
        )
        new_snap = apply_user_overrides(snap, {"core_loop": None})

        assert new_snap.get_topic("core_loop").user_override is None
        assert new_snap.get_topic("core_loop").effective_score == 0.5


# ---------------------------------------------------------------------------
# JSON persistence
# ---------------------------------------------------------------------------

class TestClarityJsonPersistence:
    """Tests for save_clarity_json() and load_clarity_json()."""

    def test_save_and_load_round_trip(self, tmp_path):
        topics = [
            TopicClarity(
                topic="core_loop", display_name="Core loop", score=0.7,
                answered_count=7, total_count=10, challenged_count=1,
            ),
            TopicClarity(
                topic="art", display_name="Art", score=0.4,
                answered_count=2, total_count=5, challenged_count=0,
                user_override=0.8,
            ),
        ]
        snap = ClaritySnapshot(
            topics=topics,
            context=ClarityContext(scope_label="broad", scope_description="Test"),
            created_iso="2026-03-19T00:00:00Z",
            run_id="run_market_20260319_000000",
        )
        json_path = tmp_path / "clarity.json"
        save_clarity_json(json_path, snap)
        loaded = load_clarity_json(json_path)

        assert loaded is not None
        assert len(loaded.topics) == 2
        assert loaded.topics[0].topic == "core_loop"
        assert loaded.topics[0].score == pytest.approx(0.7)
        assert loaded.topics[1].user_override == 0.8
        assert loaded.run_id == "run_market_20260319_000000"
        assert loaded.context.scope_label == "broad"

    def test_load_missing_returns_none(self, tmp_path):
        result = load_clarity_json(tmp_path / "nonexistent.json")
        assert result is None

    def test_schema_version_present(self, tmp_path):
        """Saved JSON file contains a schema_version field."""
        import json

        snap = ClaritySnapshot(
            topics=[],
            context=ClarityContext(scope_label="broad", scope_description="T"),
            created_iso="2026-03-19T00:00:00Z",
        )
        json_path = tmp_path / "clarity.json"
        save_clarity_json(json_path, snap)

        assert json_path.exists()
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert "schema_version" in data


# ---------------------------------------------------------------------------
# Project clarity (.studio/clarity.json)
# ---------------------------------------------------------------------------

class TestProjectClarity:
    """Tests for load_project_clarity() and save_project_clarity()."""

    def test_save_and_load_from_studio_dir(self, tmp_path):
        artifact_root = tmp_path / "project"
        artifact_root.mkdir()
        studio_dir = artifact_root / ".studio"
        studio_dir.mkdir()

        snap = ClaritySnapshot(
            topics=[
                TopicClarity(
                    topic="core_loop", display_name="Core loop", score=0.6,
                    answered_count=3, total_count=5, challenged_count=0,
                ),
            ],
            context=ClarityContext(scope_label="broad", scope_description="T"),
            created_iso="2026-03-19T00:00:00Z",
        )
        save_project_clarity(artifact_root, snap)
        loaded = load_project_clarity(artifact_root)

        assert loaded is not None
        assert len(loaded.topics) == 1
        assert loaded.topics[0].topic == "core_loop"

    def test_load_missing_returns_none(self, tmp_path):
        artifact_root = tmp_path / "empty_project"
        artifact_root.mkdir()
        result = load_project_clarity(artifact_root)
        assert result is None
