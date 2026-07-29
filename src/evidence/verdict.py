"""verdict.py — the three-valued algebra, and the one rule that makes an aggregate honest.

THE RULE: **the aggregate is the weakest leg, never the mean.**

This is the whole reason the package exists, so it is worth being precise about why the obvious
implementations are wrong.

    Averaging is wrong.       Four checks that passed and one that could not run is not "80%
                              verified". It is unverified, with four things known about it.
    Counting passes is wrong. "3 PASS, 1 ABSTAIN" reads like a score. Nobody reading a score
                              notices that the one abstention was the trust anchor.
    Majority is wrong.        A property is not more true because more tools agree it might be.

Evidence does not add up. A chain of reasoning is exactly as strong as its weakest link, and an
aggregate that reports anything stronger than its weakest constituent has manufactured confidence
that no constituent earned.

THE ORDERING, weakest to strongest:

    FAILED       a check ran and the property does not hold        (exit 1)
    UNVERIFIED   a check could not be completed; nothing is known  (exit 2)
    PASSED       a check ran and the property holds                (exit 0)

`FAILED` is weakest because it is the only value that reports a known defect. `UNVERIFIED` sits
above it because "we do not know" is not as bad as "we know it is broken" -- but it is strictly
below `PASSED`, and no number of passes can lift it.

NOT_APPLICABLE IS NOT A VERDICT. A tool with nothing to look at has said nothing. Folding it in
as an abstention would make every repository permanently UNVERIFIED, which is a verdict so
uninformative that users would learn to ignore it -- and a warning people ignore is worse than no
warning. So it is excluded from the aggregation and reported separately, as COVERAGE.

But it cannot simply vanish either, and this is the sharp edge: if NOTHING is applicable, the
aggregation is over an empty set, and `all([])` is True. That is the vacuous-pass bug this whole
portfolio exists to prevent, reappearing one level up at the aggregator. So an aggregate over zero
applicable constituents is UNVERIFIED, always, and says why.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

PASSED = "PASSED"
FAILED = "FAILED"
UNVERIFIED = "UNVERIFIED"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNAVAILABLE = "UNAVAILABLE"

#: Weakest first. `min` over this ordering IS the aggregation rule.
ORDER: List[str] = [FAILED, UNVERIFIED, PASSED]

#: The portfolio-wide exit-code dialect: 0 checked and holds, 1 checked and fails, 2 NOT checked.
EXIT = {PASSED: 0, FAILED: 1, UNVERIFIED: 2, NOT_APPLICABLE: 2, UNAVAILABLE: 2}

#: What a constituent's own exit code means, in the same dialect. Anything else is UNVERIFIED:
#: an unrecognised exit code is precisely the situation where we do not know what happened.
FROM_EXIT = {0: PASSED, 1: FAILED, 2: UNVERIFIED}


def strength(verdict: str) -> int:
    """Position in the weakest-to-strongest ordering. Non-aggregating values sort above all."""
    return ORDER.index(verdict) if verdict in ORDER else len(ORDER)


@dataclass
class LegResult:
    """One constituent's contribution to the audit."""

    tool: str
    verdict: str
    detail: str = ""
    evidence: str = ""                       # what it actually looked at
    bound: Optional[str] = None              # the constituent's own error bar, if it has one
    exit_code: Optional[int] = None          # what the tool returned, verbatim
    raw: Optional[dict] = None

    @property
    def aggregating(self) -> bool:
        """Only a leg that actually checked something votes."""
        return self.verdict in ORDER

    def to_dict(self) -> Dict:
        return {"tool": self.tool, "verdict": self.verdict, "detail": self.detail,
                "evidence": self.evidence, "bound": self.bound,
                "constituent_exit_code": self.exit_code, "aggregating": self.aggregating}


@dataclass
class Aggregate:
    """The audit's single answer, and the accounting behind it."""

    verdict: str
    reason: str
    legs: List[LegResult] = field(default_factory=list)
    weakest: Optional[str] = None            # which tool set the verdict

    @property
    def exit_code(self) -> int:
        return EXIT[self.verdict]

    @property
    def coverage(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for leg in self.legs:
            counts[leg.verdict] = counts.get(leg.verdict, 0) + 1
        return counts

    def to_dict(self) -> Dict:
        return {
            "artifact": "evidence_audit",
            "verdict": self.verdict,
            "exit_code": self.exit_code,
            "reason": self.reason,
            "weakest_leg": self.weakest,
            "aggregation_rule": "the weakest leg, never the mean",
            "coverage": self.coverage,
            "legs": [leg.to_dict() for leg in self.legs],
            "does_not_prove": DOES_NOT_PROVE,
        }


DOES_NOT_PROVE = [
    "that the constituents cover everything worth checking — an audit is exactly as broad as the "
    "tools that ran, and a PASSED aggregate over two legs is a narrow statement",
    "that a NOT_APPLICABLE leg found nothing wrong; it looked for nothing, which is different",
    "anything a constituent's own scope section disclaims — this aggregate inherits every limit "
    "of every leg it summarises, and adds no confidence of its own",
]


def aggregate(legs: Sequence[LegResult]) -> Aggregate:
    """Combine legs into one verdict: the weakest that actually checked something.

    The empty case is the one that matters. `min` over an empty sequence has no answer, and every
    tempting default -- PASSED because nothing failed, or silently dropping the audit -- is the
    vacuous pass this portfolio exists to prevent.
    """
    legs = list(legs)
    voting = [leg for leg in legs if leg.aggregating]

    if not legs:
        return Aggregate(UNVERIFIED, "no constituent tools were run, so nothing was checked", legs)

    if not voting:
        n_na = sum(1 for leg in legs if leg.verdict == NOT_APPLICABLE)
        n_un = sum(1 for leg in legs if leg.verdict == UNAVAILABLE)
        bits = []
        if n_na:
            bits.append(f"{n_na} found nothing here to check")
        if n_un:
            bits.append(f"{n_un} could not be run")
        return Aggregate(
            UNVERIFIED,
            "not one constituent checked anything (" + "; ".join(bits) + "). "
            "An aggregate over zero checks is not a pass — it is an absence of evidence.",
            legs)

    weakest_leg = min(voting, key=lambda leg: strength(leg.verdict))
    verdict = weakest_leg.verdict
    n_pass = sum(1 for leg in voting if leg.verdict == PASSED)

    if verdict == PASSED:
        skipped = len(legs) - len(voting)
        reason = (f"all {n_pass} constituent(s) that had something to check passed"
                  + (f"; {skipped} had nothing to check and did not vote" if skipped else ""))
    else:
        reason = (f"{weakest_leg.tool} is {verdict}, and the aggregate is the weakest leg — "
                  f"{n_pass} other constituent(s) passing does not lift it")

    return Aggregate(verdict, reason, legs, weakest=weakest_leg.tool)


__all__ = ["PASSED", "FAILED", "UNVERIFIED", "NOT_APPLICABLE", "UNAVAILABLE", "ORDER", "EXIT",
           "FROM_EXIT", "LegResult", "Aggregate", "aggregate", "strength", "DOES_NOT_PROVE"]
