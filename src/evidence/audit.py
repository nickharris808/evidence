"""audit.py — run the applicable constituents over a tree and render one aggregate."""
from __future__ import annotations

import os
from typing import List, Optional, Sequence

from .constituents import NOT_AUTOMATABLE, REGISTRY, Constituent
from .verdict import (DOES_NOT_PROVE, FAILED, NOT_APPLICABLE, PASSED, UNAVAILABLE, UNVERIFIED,
                      Aggregate, LegResult, aggregate)

MARK = {PASSED: "PASS", FAILED: "FAIL", UNVERIFIED: "UNVERIFIED",
        NOT_APPLICABLE: "n/a", UNAVAILABLE: "MISSING"}


def audit(root: str, only: Optional[Sequence[str]] = None, timeout: int = 300,
          registry: Optional[Sequence[Constituent]] = None) -> Aggregate:
    """Evaluate every constituent against `root` and aggregate to the weakest leg."""
    if not os.path.isdir(root):
        return Aggregate(UNVERIFIED, f"{root} is not a directory; nothing was audited", [])
    chosen = [c for c in (registry or REGISTRY) if not only or c.name in only]
    legs: List[LegResult] = [c.evaluate(root, timeout=timeout) for c in chosen]
    return aggregate(legs)


def render(agg: Aggregate, root: str = ".", show_excluded: bool = False) -> str:
    """The human report. Ordered weakest first, because the weakest leg IS the answer."""
    width = 76
    out: List[str] = []
    order = {PASSED: 3, NOT_APPLICABLE: 2, UNAVAILABLE: 1, UNVERIFIED: 0, FAILED: -1}
    for leg in sorted(agg.legs, key=lambda x: (order.get(x.verdict, 0), x.tool)):
        mark = MARK.get(leg.verdict, leg.verdict)
        detail = leg.detail or ""
        if len(detail) > 44:
            detail = detail[:41] + "..."
        out.append(f"  {leg.tool:<14} {detail:<46} [{mark}]")
        if leg.bound:
            out.append(f"  {'':<14} bound {leg.bound}")

    out.append("  " + "-" * (width - 2))
    cov = agg.coverage
    parts = [f"{n} {MARK.get(v, v).lower()}" for v, n in
             sorted(cov.items(), key=lambda kv: order.get(kv[0], 0))]
    out.append(f"  AGGREGATE: {agg.verdict} — " + ", ".join(parts))
    out.append(f"  {agg.reason}")
    out.append("  The aggregate is the WEAKEST leg, never the mean.")

    if any(leg.verdict == UNAVAILABLE for leg in agg.legs):
        out.append("")
        out.append("  Some constituents are not installed. They did not vote, so they could not")
        out.append("  weaken this verdict — but they could not strengthen it either, and the")
        out.append("  scope of this audit is only the tools that actually ran.")

    if show_excluded:
        out.append("")
        out.append("  Not auto-run, and why:")
        for name, why in sorted(NOT_AUTOMATABLE.items()):
            out.append(f"    {name:<28} {why}")

    out.append("")
    out.append("  This does NOT prove:")
    for line in DOES_NOT_PROVE:
        out.append(f"    - {line}")
    return "\n".join(out)


__all__ = ["audit", "render", "MARK"]
