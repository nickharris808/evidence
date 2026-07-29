"""The aggregation rule, which is the whole package.

The plan that motivated this work flagged this file's subject before it was written:

    `evidence` aggregation is the highest-risk new code here. The tempting implementation
    averages or counts passes; the correct one propagates the weakest leg. A test must assert
    that one ABSTAIN among four PASSes yields ABSTAIN.

So that test is here, and so are the two adjacent mistakes: an aggregate over an empty set (which
`all([])` makes True) and an aggregate whose scope silently depends on which tools happened to be
installed on the machine that ran it.
"""
from __future__ import annotations

import pytest

from evidence.verdict import (FAILED, NOT_APPLICABLE, PASSED, UNAVAILABLE, UNVERIFIED,
                              LegResult, aggregate, strength)


def leg(tool, verdict, **kw):
    return LegResult(tool, verdict, **kw)


# ------------------------------------------------------------------ the rule

def test_one_unverified_among_four_passes_yields_unverified():
    """The case the plan named. Four checks that passed and one that could not run is not
    "80% verified"; it is unverified, with four things known about it."""
    legs = [leg(f"t{i}", PASSED) for i in range(4)] + [leg("anchor", UNVERIFIED)]
    agg = aggregate(legs)
    assert agg.verdict == UNVERIFIED
    assert agg.weakest == "anchor"
    assert agg.exit_code == 2


def test_one_failure_among_many_passes_yields_failed():
    agg = aggregate([leg(f"t{i}", PASSED) for i in range(9)] + [leg("bad", FAILED)])
    assert agg.verdict == FAILED
    assert agg.weakest == "bad"
    assert agg.exit_code == 1


def test_failed_outranks_unverified_as_the_weakest_leg():
    agg = aggregate([leg("a", UNVERIFIED), leg("b", FAILED), leg("c", PASSED)])
    assert agg.verdict == FAILED, "a known defect is weaker than an unknown"
    assert strength(FAILED) < strength(UNVERIFIED) < strength(PASSED)


def test_all_pass_yields_pass():
    agg = aggregate([leg("a", PASSED), leg("b", PASSED)])
    assert agg.verdict == PASSED
    assert agg.exit_code == 0


def test_the_aggregate_is_never_the_mean():
    """Explicitly: no combination of passes can average away a weaker leg."""
    for n_pass in range(1, 20):
        agg = aggregate([leg(f"p{i}", PASSED) for i in range(n_pass)] + [leg("x", UNVERIFIED)])
        assert agg.verdict == UNVERIFIED, f"{n_pass} passes lifted an UNVERIFIED"


def test_the_reason_names_the_leg_that_set_the_verdict():
    agg = aggregate([leg("a", PASSED), leg("trust-anchor", UNVERIFIED)])
    assert "trust-anchor" in agg.reason
    assert "weakest leg" in agg.reason


# ------------------------------------------------------------------ the vacuous cases

def test_an_aggregate_over_zero_legs_abstains():
    """`all([])` is True. That is the bug this portfolio exists to prevent, one level up."""
    agg = aggregate([])
    assert agg.verdict == UNVERIFIED
    assert agg.exit_code == 2
    assert "nothing was checked" in agg.reason


def test_an_aggregate_where_nothing_was_applicable_abstains():
    agg = aggregate([leg("a", NOT_APPLICABLE), leg("b", NOT_APPLICABLE)])
    assert agg.verdict == UNVERIFIED, (
        "five tools that found nothing to look at have not established anything")
    assert "not one constituent checked anything" in agg.reason


def test_an_aggregate_where_every_tool_was_missing_abstains():
    agg = aggregate([leg("a", UNAVAILABLE), leg("b", UNAVAILABLE)])
    assert agg.verdict == UNVERIFIED
    assert "could not be run" in agg.reason


def test_not_applicable_does_not_drag_a_real_pass_down():
    """Otherwise every repository is permanently UNVERIFIED, and a verdict nobody can ever
    satisfy is a verdict everybody learns to ignore."""
    agg = aggregate([leg("a", PASSED), leg("b", NOT_APPLICABLE), leg("c", NOT_APPLICABLE)])
    assert agg.verdict == PASSED
    assert "2 had nothing to check and did not vote" in agg.reason


def test_a_missing_tool_neither_lifts_nor_lowers_the_verdict():
    with_missing = aggregate([leg("a", PASSED), leg("b", UNAVAILABLE)])
    without = aggregate([leg("a", PASSED)])
    assert with_missing.verdict == without.verdict == PASSED
    assert with_missing.coverage[UNAVAILABLE] == 1, "but it must still be visible in coverage"


def test_coverage_accounts_for_every_leg():
    legs = [leg("a", PASSED), leg("b", FAILED), leg("c", NOT_APPLICABLE), leg("d", UNAVAILABLE)]
    agg = aggregate(legs)
    assert sum(agg.coverage.values()) == 4, "no leg may vanish from the accounting"


# ------------------------------------------------------------------ the serialised contract

def test_json_carries_the_rule_and_the_limits():
    d = aggregate([leg("a", PASSED)]).to_dict()
    assert d["aggregation_rule"] == "the weakest leg, never the mean"
    assert d["does_not_prove"], "the aggregate must state what it does not establish"
    assert d["exit_code"] == 0


def test_json_verdict_and_exit_code_never_disagree():
    for verdict, code in ((PASSED, 0), (FAILED, 1), (UNVERIFIED, 2)):
        legs = [leg("a", verdict)] if verdict in (PASSED, FAILED) else []
        d = aggregate(legs).to_dict()
        assert d["exit_code"] == code, f"{d['verdict']} reported exit {d['exit_code']}"


@pytest.mark.parametrize("verdict", [PASSED, FAILED, UNVERIFIED])
def test_a_single_leg_is_its_own_aggregate(verdict):
    agg = aggregate([leg("solo", verdict)])
    assert agg.verdict == verdict
