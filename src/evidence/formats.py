"""formats.py — render an aggregate as SARIF, JUnit, Markdown or JSON.

WHY THIS EXISTS. A verdict nobody sees is a verdict nobody acts on. GitHub renders SARIF natively
in the Security tab and JUnit in the checks UI, and both are cheap to emit; a bespoke text format
means every consumer writes glue, and most of them do not.

THE ONE RULE THAT SURVIVES EVERY FORMAT: an UNVERIFIED must never render as a pass. That is easy
to get wrong here, because both target schemas have a natural "everything is fine" shape --
zero SARIF results, zero JUnit failures -- and an audit that could not check anything produces
exactly zero findings. So:

    SARIF   an UNVERIFIED aggregate emits a `warning`-level result. Not `none`, which some
            viewers hide, and not `error`, which would claim a defect was found.
    JUnit   an UNVERIFIED leg is an `<error>`, distinct from a `<failure>`. JUnit has had that
            distinction since the beginning and it means exactly what is needed here: a failure
            is a test that ran and failed, an error is a test that could not run.

`skipped` is deliberately NOT used for UNVERIFIED. A skipped test is one nobody wanted to run;
an unverified check is one that was wanted and could not be completed, and CI dashboards colour
those very differently.
"""
from __future__ import annotations

import json
from typing import Dict, List
from xml.sax.saxutils import escape, quoteattr

from .verdict import FAILED, NOT_APPLICABLE, PASSED, UNAVAILABLE, UNVERIFIED, Aggregate

SARIF_LEVEL = {FAILED: "error", UNVERIFIED: "warning", UNAVAILABLE: "warning",
               NOT_APPLICABLE: "note", PASSED: "note"}


def to_sarif(agg: Aggregate, root: str = ".", version: str = "0") -> str:
    """SARIF 2.1.0. Every leg becomes a result, including the ones that passed.

    Passing legs are emitted at `note` level rather than omitted, because a SARIF file with no
    results is indistinguishable from a run that checked nothing — which is the exact ambiguity
    this portfolio refuses everywhere else.
    """
    rules: List[Dict] = []
    results: List[Dict] = []
    for leg in agg.legs:
        rule_id = f"evidence/{leg.tool}"
        rules.append({
            "id": rule_id,
            "name": leg.tool.replace("-", "_"),
            "shortDescription": {"text": f"{leg.tool} verdict"},
            "fullDescription": {"text": leg.detail or f"{leg.tool} produced {leg.verdict}"},
            "defaultConfiguration": {"level": SARIF_LEVEL.get(leg.verdict, "warning")},
        })
        results.append({
            "ruleId": rule_id,
            "level": SARIF_LEVEL.get(leg.verdict, "warning"),
            "message": {"text": f"{leg.verdict}: {leg.detail or 'no detail reported'}"
                                + (f" [bound {leg.bound}]" if leg.bound else "")},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": root.replace("\\", "/").lstrip("./") or "."}}}],
            "properties": {"verdict": leg.verdict, "aggregating": leg.aggregating,
                           "evidence": leg.evidence},
        })

    rules.append({
        "id": "evidence/aggregate",
        "name": "aggregate",
        "shortDescription": {"text": "portfolio aggregate verdict"},
        "fullDescription": {"text": "The weakest leg, never the mean."},
        "defaultConfiguration": {"level": SARIF_LEVEL.get(agg.verdict, "warning")},
    })
    results.append({
        "ruleId": "evidence/aggregate",
        "level": SARIF_LEVEL.get(agg.verdict, "warning"),
        "message": {"text": f"AGGREGATE {agg.verdict}: {agg.reason}"},
        "locations": [{"physicalLocation": {
            "artifactLocation": {"uri": root.replace("\\", "/").lstrip("./") or "."}}}],
        "properties": {"verdict": agg.verdict, "weakest_leg": agg.weakest,
                       "aggregation_rule": "the weakest leg, never the mean"},
    })

    return json.dumps({
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "evidence",
                "version": version,
                "informationUri": "https://github.com/nickharris808/evidence",
                "rules": rules,
            }},
            "results": results,
        }],
    }, indent=2)


def to_junit(agg: Aggregate, root: str = ".") -> str:
    """JUnit XML. `failure` for a real negative, `error` for could-not-check — never `skipped`."""
    failures = sum(1 for leg in agg.legs if leg.verdict == FAILED)
    errors = sum(1 for leg in agg.legs if leg.verdict in (UNVERIFIED, UNAVAILABLE))
    skipped = sum(1 for leg in agg.legs if leg.verdict == NOT_APPLICABLE)
    total = len(agg.legs) + 1                      # + the aggregate itself

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append(f'<testsuites name="evidence" tests="{total}" failures="{failures}" '
                 f'errors="{errors}" skipped="{skipped}">')
    lines.append(f'  <testsuite name="evidence.audit" tests="{total}" failures="{failures}" '
                 f'errors="{errors}" skipped="{skipped}">')
    for leg in agg.legs:
        msg = quoteattr(f"{leg.verdict}: {leg.detail or ''}"[:900])
        lines.append(f'    <testcase classname="evidence" name={quoteattr(leg.tool)}>')
        if leg.verdict == FAILED:
            lines.append(f'      <failure message={msg} type="checked-and-failed"/>')
        elif leg.verdict in (UNVERIFIED, UNAVAILABLE):
            lines.append(f'      <error message={msg} type="not-checked"/>')
        elif leg.verdict == NOT_APPLICABLE:
            lines.append(f'      <skipped message={msg}/>')
        lines.append("    </testcase>")

    agg_msg = quoteattr(f"{agg.verdict}: {agg.reason}"[:900])
    lines.append('    <testcase classname="evidence" name="AGGREGATE">')
    if agg.verdict == FAILED:
        lines.append(f'      <failure message={agg_msg} type="checked-and-failed"/>')
    elif agg.verdict == UNVERIFIED:
        lines.append(f'      <error message={agg_msg} type="not-checked"/>')
    lines.append("    </testcase>")
    lines.append(f"    <system-out>{escape(agg.reason)}</system-out>")
    lines.append("  </testsuite>")
    lines.append("</testsuites>")
    return "\n".join(lines)


def to_markdown(agg: Aggregate, root: str = ".") -> str:
    """A GitHub job summary. Written to be readable when it is the only thing anyone opens."""
    icon = {PASSED: "✅", FAILED: "❌", UNVERIFIED: "⚠️", NOT_APPLICABLE: "➖",
            UNAVAILABLE: "❓"}
    out = [f"## evidence: **{agg.verdict}**", "", f"> {agg.reason}", "",
           "The aggregate is the **weakest leg**, never the mean.", "",
           "| constituent | verdict | what it looked at | detail |",
           "|---|---|---|---|"]
    for leg in sorted(agg.legs, key=lambda x: x.tool):
        out.append(f"| `{leg.tool}` | {icon.get(leg.verdict, '')} {leg.verdict} | "
                   f"{leg.evidence or '—'} | {leg.detail or '—'} |")
    out += ["", "<details><summary>What this does not prove</summary>", ""]
    from .verdict import DOES_NOT_PROVE
    for line in DOES_NOT_PROVE:
        out.append(f"- {line}")
    out += ["", "</details>"]
    return "\n".join(out)


FORMATS = {"json", "sarif", "junit", "markdown", "text"}

__all__ = ["to_sarif", "to_junit", "to_markdown", "FORMATS", "SARIF_LEVEL"]
