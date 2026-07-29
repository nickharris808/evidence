"""End-to-end audits, the pipeline contract, and the four output formats.

The format tests exist because both SARIF and JUnit have a natural "everything is fine" shape --
zero results, zero failures -- and an audit that could not check anything produces exactly zero
findings. An UNVERIFIED that renders as a clean report is the vacuous pass wearing a CI badge.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from evidence.audit import audit, render
from evidence.constituents import Constituent, Subject, walk
from evidence.formats import to_junit, to_markdown, to_sarif
from evidence.verdict import (FAILED, NOT_APPLICABLE, PASSED, UNAVAILABLE, UNVERIFIED,
                              LegResult, aggregate)

HAS_GRIDLOCK = shutil.which("gridlock") is not None

LOCK_CYCLE = """
import threading
a_lock = threading.Lock()
b_lock = threading.Lock()
def f():
    with a_lock:
        with b_lock:
            pass
def g():
    with b_lock:
        with a_lock:
            pass
"""


def _fake(name, script, detect=None, **kw):
    """A constituent backed by a throwaway Python script, so exit codes are exactly controlled."""
    return Constituent(
        name=name, binary=sys.executable,
        scope="test double",
        detect=detect or (lambda root: Subject([os.path.join(root, "x")])),
        invoke=lambda root, s: [sys.executable, "-c", script], **kw)


# ------------------------------------------------------------------ exit-code translation

def test_exit_zero_one_two_map_to_the_three_verdicts(tmp_path):
    (tmp_path / "x").write_text("")
    for code, verdict in ((0, PASSED), (1, FAILED), (2, UNVERIFIED)):
        c = _fake("t", f"import sys; sys.exit({code})")
        assert c.evaluate(str(tmp_path)).verdict == verdict


def test_an_exit_code_outside_the_dialect_is_unverified_not_failed(tmp_path):
    """Mapping 'not 0' to FAILED invents a finding out of a crash."""
    (tmp_path / "x").write_text("")
    leg = _fake("t", "import sys; sys.exit(42)").evaluate(str(tmp_path))
    assert leg.verdict == UNVERIFIED
    assert "outside the 0/1/2 dialect" in leg.detail


def test_a_tool_that_is_not_installed_is_unavailable_and_does_not_vote(tmp_path):
    c = Constituent(name="ghost", binary="definitely-not-a-real-binary-xyz", scope="",
                    detect=lambda root: Subject(["x"]), invoke=lambda root, s: ["x"])
    leg = c.evaluate(str(tmp_path))
    assert leg.verdict == UNAVAILABLE
    assert not leg.aggregating, "a missing tool must not vote in either direction"


def test_a_timeout_is_unverified_not_failed(tmp_path):
    (tmp_path / "x").write_text("")
    c = _fake("slow", "import time; time.sleep(30)")
    leg = c.evaluate(str(tmp_path), timeout=1)
    assert leg.verdict == UNVERIFIED
    assert "timed out" in leg.detail


def test_nothing_to_look_at_is_not_applicable(tmp_path):
    c = Constituent(name="t", binary=sys.executable, scope="",
                    detect=lambda root: Subject([], note="nothing here"),
                    invoke=lambda root, s: [sys.executable, "-c", "pass"])
    leg = c.evaluate(str(tmp_path))
    assert leg.verdict == NOT_APPLICABLE
    assert not leg.aggregating


# ------------------------------------------------------------------ the pipeline contract

def test_a_pipeline_takes_its_verdict_from_the_last_stage(tmp_path):
    """The defect this feature exists for: running only stage one and reporting its exit code
    answers a different question from the one asked."""
    (tmp_path / "x").write_text("")
    c = Constituent(
        name="two-stage", binary=sys.executable, scope="",
        detect=lambda root: Subject(["x"]),
        invoke=lambda root, s: [[sys.executable, "-c", "print('{}')"],
                                [sys.executable, "-c", "import sys; sys.exit(1)"]])
    assert c.evaluate(str(tmp_path)).verdict == FAILED, (
        "stage one succeeding must not become the leg's verdict")


def test_an_abstaining_first_stage_abstains_the_whole_pipeline(tmp_path):
    """An importer that refused must not have its refusal overwritten downstream."""
    (tmp_path / "x").write_text("")
    c = Constituent(
        name="refuser", binary=sys.executable, scope="",
        detect=lambda root: Subject(["x"]),
        invoke=lambda root, s: [[sys.executable, "-c",
                                 "import sys; sys.stderr.write('refused\\n'); sys.exit(2)"],
                                [sys.executable, "-c", "import sys; sys.exit(0)"]])
    leg = c.evaluate(str(tmp_path))
    assert leg.verdict == UNVERIFIED, "a refusal must not be laundered into a pass"
    assert "abstained" in leg.detail


# ------------------------------------------------------------------ end to end

def test_an_empty_tree_abstains(tmp_path):
    agg = audit(str(tmp_path))
    assert agg.verdict == UNVERIFIED
    assert agg.exit_code == 2


def test_a_path_that_is_not_a_directory_abstains(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hi")
    agg = audit(str(f))
    assert agg.verdict == UNVERIFIED
    assert "not a directory" in agg.reason


@pytest.mark.skipif(not HAS_GRIDLOCK, reason="gridlock not installed")
def test_a_real_lock_cycle_is_found_and_fails_the_aggregate(tmp_path):
    (tmp_path / "m.py").write_text(LOCK_CYCLE)
    agg = audit(str(tmp_path), only=["gridlock"])
    assert agg.verdict == FAILED
    assert agg.exit_code == 1
    leg = agg.legs[0]
    assert "WEDGES" in leg.detail


@pytest.mark.skipif(not HAS_GRIDLOCK, reason="gridlock not installed")
def test_python_sources_with_no_locks_abstain_rather_than_pass(tmp_path):
    """The importer refuses; the leg must inherit the refusal, not report a clean bill."""
    (tmp_path / "plain.py").write_text("def add(a, b):\n    return a + b\n")
    agg = audit(str(tmp_path), only=["gridlock"])
    assert agg.verdict == UNVERIFIED, "no locks found is not the same as no deadlock"


def test_render_names_the_rule_and_the_limits(tmp_path):
    text = render(audit(str(tmp_path)), str(tmp_path))
    assert "WEAKEST leg, never the mean" in text
    assert "does NOT prove" in text


# ------------------------------------------------------------------ formats

def _agg_unverified():
    return aggregate([LegResult("a", PASSED, detail="fine"),
                      LegResult("anchor", UNVERIFIED, detail="no trust anchor")])


def test_sarif_is_valid_json_with_the_required_shape():
    d = json.loads(to_sarif(_agg_unverified(), "."))
    assert d["version"] == "2.1.0"
    assert d["runs"][0]["tool"]["driver"]["name"] == "evidence"
    for r in d["runs"][0]["results"]:
        assert r["ruleId"] and r["message"]["text"] and r["level"]


def test_sarif_emits_a_warning_for_an_unverified_aggregate_not_silence():
    """Zero results is how SARIF says 'clean'. An audit that checked nothing must not say that."""
    d = json.loads(to_sarif(_agg_unverified(), "."))
    agg_results = [r for r in d["runs"][0]["results"] if r["ruleId"] == "evidence/aggregate"]
    assert len(agg_results) == 1
    assert agg_results[0]["level"] == "warning"
    assert "UNVERIFIED" in agg_results[0]["message"]["text"]


def test_sarif_emits_passing_legs_too():
    """A SARIF file with no results is indistinguishable from a run that checked nothing."""
    d = json.loads(to_sarif(aggregate([LegResult("a", PASSED)]), "."))
    assert len(d["runs"][0]["results"]) == 2, "one leg + the aggregate"


def test_sarif_levels_never_call_an_unverified_clean():
    d = json.loads(to_sarif(_agg_unverified(), "."))
    levels = {r["properties"].get("verdict"): r["level"] for r in d["runs"][0]["results"]
              if "verdict" in r.get("properties", {})}
    assert levels[UNVERIFIED] == "warning"
    assert levels.get(PASSED) == "note"


def test_junit_distinguishes_could_not_check_from_checked_and_failed():
    xml = to_junit(aggregate([LegResult("broke", FAILED), LegResult("unknown", UNVERIFIED)]), ".")
    root = ET.fromstring(xml)
    suite = root.find("testsuite")
    assert suite.get("failures") == "1"
    assert suite.get("errors") == "1", "an unverified check is an ERROR, not a failure"
    kinds = {tc.get("name"): [c.tag for c in tc] for tc in suite.findall("testcase")}
    assert kinds["broke"] == ["failure"]
    assert kinds["unknown"] == ["error"]


def test_junit_never_marks_an_unverified_as_skipped():
    """CI dashboards colour a skip as 'nobody wanted this'. That is the wrong story."""
    xml = to_junit(aggregate([LegResult("unknown", UNVERIFIED)]), ".")
    assert "<skipped" not in xml
    assert ET.fromstring(xml) is not None


def test_junit_is_well_formed_with_hostile_characters():
    legs = [LegResult('we"ird & <bad>', FAILED, detail='a "quoted" <thing> & more')]
    ET.fromstring(to_junit(aggregate(legs), "."))


def test_markdown_leads_with_the_verdict_and_the_rule():
    md = to_markdown(_agg_unverified(), ".")
    assert md.startswith("## evidence: **UNVERIFIED**")
    assert "weakest leg" in md
    assert "What this does not prove" in md


@pytest.mark.parametrize("fmt", ["json", "sarif", "junit", "markdown", "text"])
def test_every_format_reports_the_same_verdict(tmp_path, fmt):
    """A format that disagrees with another about the verdict is a format that lies to someone."""
    out = subprocess.run([sys.executable, "-m", "evidence.cli", "audit", str(tmp_path),
                          "--format", fmt], capture_output=True, text=True)
    assert out.returncode == 2, f"{fmt} run changed the exit code"
    assert "UNVERIFIED" in out.stdout, f"{fmt} did not carry the verdict"


def test_cli_rejects_an_unknown_constituent(tmp_path):
    out = subprocess.run([sys.executable, "-m", "evidence.cli", "audit", str(tmp_path),
                          "--only", "nope"], capture_output=True, text=True)
    assert out.returncode == 2
    assert "unknown constituent" in out.stderr


def test_cli_tools_lists_what_is_excluded_and_why():
    out = subprocess.run([sys.executable, "-m", "evidence.cli", "tools"],
                         capture_output=True, text=True)
    assert out.returncode == 0
    assert "kvleak" in out.stdout and "live inference endpoint" in out.stdout


# ------------------------------------------------------------------ detection hygiene

def test_walk_skips_vendored_trees(tmp_path):
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "a.py").write_text("x = 1")
    (tmp_path / "mine.py").write_text("y = 2")
    found = walk(str(tmp_path), suffixes=(".py",))
    assert [os.path.basename(p) for p in found.paths] == ["mine.py"]


def test_a_truncated_scan_says_so(tmp_path, monkeypatch):
    """Silent truncation reads as 'covered everything' when it did not."""
    import evidence.constituents as C
    monkeypatch.setattr(C, "MAX_FILES", 3)
    for i in range(10):
        (tmp_path / f"f{i}.py").write_text("x = 1")
    found = C.walk(str(tmp_path), suffixes=(".py",))
    assert found.truncated
