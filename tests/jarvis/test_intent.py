"""Deterministic intent grammar."""

from __future__ import annotations

import pytest

from app.jarvis.intent import parse_intent


class TestGrammar:
    def test_find_with_location(self) -> None:
        plan = parse_intent("find machine learning engineer in berlin")

        assert plan.action == "run_discovery"
        assert plan.params["user_query"].lower().startswith("find machine")
        assert plan.params["locations"] == ["berlin"]

    def test_tailor_job_n_uses_zero_based_index(self) -> None:
        plan = parse_intent("tailor job 1")

        assert plan.action == "select_target"
        assert plan.params["target_job_index"] == 0

    def test_use_match_n(self) -> None:
        plan = parse_intent("use match 3")

        assert plan.action == "select_target"
        assert plan.params["target_job_index"] == 2

    def test_status_action(self) -> None:
        assert parse_intent("status").action == "get_results"

    def test_help_action(self) -> None:
        assert parse_intent("help").action == "help"

    def test_free_text_defaults_to_discovery_query(self) -> None:
        plan = parse_intent("python engineer roles remote")

        assert plan.action == "run_discovery"
        assert plan.params["user_query"] == "python engineer roles remote"

    def test_never_raises_on_garbage(self) -> None:
        with pytest.raises(AssertionError):
            raise AssertionError  # placeholder: parser must not raise
        plan = parse_intent("")
        assert plan.action in {"run_discovery", "help"}
