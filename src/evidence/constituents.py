"""constituents.py — which tool applies to a tree, and what it is allowed to conclude.

Each constituent declares three things:

    detect(root)   what in this tree, if anything, it can speak about
    run(subject)   how to invoke it
    a scope line   what its PASSED actually means, so the aggregate can quote it

TWO REFUSALS ARE BUILT IN HERE, both of them the same mistake wearing different clothes.

1. A TOOL THAT IS NOT INSTALLED IS `UNAVAILABLE`, NOT SKIPPED. A skipped leg vanishes from the
   report, and an aggregate assembled from the tools that happened to be importable is an
   aggregate whose scope depends on the machine it ran on. `UNAVAILABLE` is loud, and it does not
   vote -- so it cannot drag the verdict down either. It shows up in COVERAGE, where a reader can
   see that six of nine tools were missing before believing a PASSED.

2. AN UNRECOGNISED EXIT CODE IS `UNVERIFIED`. The portfolio dialect is 0/1/2. A constituent that
   returns 3, or dies on a signal, has not told us the property holds. Mapping "not 0" to FAILED
   would be just as wrong as mapping it to PASSED: it invents a finding out of a crash.

DETECTION IS DELIBERATELY CONSERVATIVE. A detector that guesses produces a leg about the wrong
subject, and a confident verdict about the wrong subject is worse than no verdict. Where a tool
needs an argument this package cannot infer -- a live endpoint, a tokenizer, a claimed count --
the constituent reports NOT_APPLICABLE and says what it would have needed.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

from .verdict import (FROM_EXIT, NOT_APPLICABLE, UNAVAILABLE, UNVERIFIED, LegResult)

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".tox", ".mypy_cache",
             "build", "dist", ".pytest_cache", ".ruff_cache"}
#: A cap on how much of a tree a detector will walk. Stated, not silent: see `Subject.truncated`.
MAX_FILES = 20000


@dataclass
class Subject:
    """What a constituent found to talk about."""

    paths: List[str]
    note: str = ""
    truncated: bool = False


def walk(root: str, suffixes: Sequence[str] = (), names: Sequence[str] = ()) -> Subject:
    """Files under `root` matching a suffix or an exact basename, vendored trees excluded."""
    hits: List[str] = []
    seen = 0
    truncated = False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in sorted(filenames):
            seen += 1
            if seen > MAX_FILES:
                truncated = True
                break
            if (suffixes and f.endswith(tuple(suffixes))) or (names and f in names):
                hits.append(os.path.join(dirpath, f))
        if truncated:
            break
    return Subject(sorted(hits), truncated=truncated)


def _exe(name: str) -> Optional[str]:
    return shutil.which(name)


def _run(cmd: List[str], cwd: Optional[str] = None, timeout: int = 300, stdin_data: str = ""):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout,
                          input=stdin_data)


@dataclass
class Constituent:
    """One tool in the audit.

    `invoke` may return EITHER one command or a list of commands forming a pipeline, stdout to
    stdin. The pipeline case exists because of a real defect caught the first time this package
    was pointed at a live tree: the gridlock leg ran `gridlock import` alone and reported PASS,
    because the import succeeded. But an import that succeeded says nothing whatever about
    deadlock — the verdict belongs to `gridlock check`, which had never run. The leg was
    reporting the exit code of the wrong question.

    So a pipeline's verdict is the LAST stage's exit code, with one exception that matters: if an
    earlier stage abstains (exit 2), the pipeline abstains. An importer that refused must not have
    its refusal overwritten by whatever the next stage makes of an empty input.
    """

    name: str
    binary: str
    scope: str                                    # what its PASSED means, in one line
    detect: Callable[[str], Subject]
    invoke: Callable[[str, Subject], List]
    install_hint: str = ""
    #: Extracts (detail, bound) from the tool's JSON, when it emits any.
    summarise: Optional[Callable[[dict], tuple]] = None

    def evaluate(self, root: str, timeout: int = 300) -> LegResult:
        path = _exe(self.binary)
        if path is None:
            return LegResult(self.name, UNAVAILABLE,
                             detail=f"`{self.binary}` is not on PATH, so this leg did not run",
                             evidence=self.install_hint or f"pip install {self.name}")
        try:
            subject = self.detect(root)
        except OSError as e:
            return LegResult(self.name, UNVERIFIED,
                             detail=f"could not read the tree ({e.strerror})")

        if not subject.paths:
            return LegResult(self.name, NOT_APPLICABLE,
                             detail=subject.note or "found nothing here it can speak about")

        spec = self.invoke(root, subject)
        stages: List[List[str]] = spec if spec and isinstance(spec[0], list) else [spec]
        stdin_data = ""
        proc = None
        try:
            for i, cmd in enumerate(stages):
                proc = _run(cmd, cwd=root, timeout=timeout, stdin_data=stdin_data)
                if i < len(stages) - 1:
                    if proc.returncode == 2:
                        # An abstaining stage must not be overwritten by the next one's opinion
                        # of an empty input. This is the whole reason the pipeline is explicit.
                        return LegResult(
                            self.name, UNVERIFIED, exit_code=2,
                            detail=(f"`{cmd[0]} {cmd[1] if len(cmd) > 1 else ''}`".strip()
                                    + " abstained, so nothing downstream could be checked: "
                                    + (_first_line(proc.stderr) or _first_line(proc.stdout))),
                            evidence=" | ".join(" ".join(c) for c in stages))
                    stdin_data = proc.stdout
        except subprocess.TimeoutExpired:
            return LegResult(self.name, UNVERIFIED,
                             detail=f"timed out after {timeout}s; no verdict was produced",
                             evidence=" | ".join(" ".join(c) for c in stages))
        except OSError as e:
            return LegResult(self.name, UNVERIFIED, detail=f"could not launch: {e}")

        cmd = stages[-1]
        verdict = FROM_EXIT.get(proc.returncode, UNVERIFIED)
        detail, bound, raw = "", None, None
        if "--json" in cmd:
            try:
                raw = json.loads(proc.stdout)
            except (json.JSONDecodeError, ValueError):
                raw = None
        if raw is not None and self.summarise:
            try:
                detail, bound = self.summarise(raw)
            except (KeyError, TypeError, ValueError):
                detail, bound = "", None
        if not detail:
            detail = _first_line(proc.stdout) or _first_line(proc.stderr) or ""
        if proc.returncode not in FROM_EXIT:
            detail = (f"exit {proc.returncode}, which is outside the 0/1/2 dialect — treating as "
                      f"UNVERIFIED rather than inventing a finding. " + detail).strip()

        n = len(subject.paths)
        ev = f"{n} file(s), e.g. {os.path.relpath(subject.paths[0], root)}"
        if subject.truncated:
            ev += f" (detection stopped at {MAX_FILES} files; the tree is larger than was scanned)"
        return LegResult(self.name, verdict, detail=detail.strip(), evidence=ev,
                         bound=bound, exit_code=proc.returncode, raw=raw)


def _first_line(s: str) -> str:
    for line in (s or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


# --------------------------------------------------------------------------- detectors

def _detect_certs(root: str) -> Subject:
    """A signoff-cert is JSON carrying the schema marker. Read the head of each candidate rather
    than trusting the filename: `cert.json` is a popular name for unrelated things."""
    cand = walk(root, suffixes=(".json",))
    hits = []
    for p in cand.paths:
        try:
            if os.path.getsize(p) > 4_000_000:
                continue
            with open(p, encoding="utf-8", errors="replace") as fh:
                head = fh.read(4096)
        except OSError:
            continue
        if "signoff-cert/v1" in head or '"false_pass_bound"' in head:
            hits.append(p)
    return Subject(hits, note="no signoff-cert/v1 certificates found", truncated=cand.truncated)


def _detect_manifest(root: str) -> Subject:
    s = walk(root, names=("MANIFEST.sha256", "manifest.sha256", "evidence.manifest.json"))
    s.note = ("no evidence manifest found (honestbench needs one: "
              "`honestbench manifest <dir> --out MANIFEST.sha256`)")
    return s


def _detect_chainlog(root: str) -> Subject:
    """A hash-chained decision log: JSONL whose first record carries a chain field."""
    cand = walk(root, suffixes=(".jsonl",))
    hits = []
    for p in cand.paths:
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                head = fh.readline(8192)
        except OSError:
            continue
        if not head.strip():
            continue
        try:
            rec = json.loads(head)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(rec, dict) and ({"prev", "prev_hash", "chain"} & set(rec)):
            hits.append(p)
    return Subject(hits, note="no hash-chained decision log (.jsonl with a `prev` field) found",
                   truncated=cand.truncated)


def _detect_wait_graph(root: str) -> Subject:
    """Python sources gridlock's lock-order importer can read. Deliberately narrow: a graph
    cannot be guessed from an arbitrary JSON file without risking a verdict about the wrong
    subject, so only the importer path is auto-detected."""
    s = walk(root, suffixes=(".py",))
    s.note = "no Python sources for the lock-order importer"
    return s


def _detect_lean(root: str) -> Subject:
    s = walk(root, suffixes=(".lean",))
    s.note = "no Lean sources, so there is no proof to drift from"
    return s


# --------------------------------------------------------------------------- summarisers

def _sum_gridlock(d: dict) -> tuple:
    v = d.get("verdict", "?")
    n, e = d.get("n_nodes", "?"), d.get("n_edges", "?")
    if v == "WEDGES" and d.get("cycle"):
        return (f"WEDGES: {' -> '.join(map(str, d['cycle']))}", None)
    return (f"{v}: {n} lock(s), {e} ordering(s)", None)


def _sum_signoff(d: dict) -> tuple:
    """Reads the `signoff_cert_verify` envelope. Names the first failing certificate rather than
    only counting: "4 of 5 verified" sends nobody to the one that did not."""
    n = d.get("n_certificates", 0)
    ok = d.get("n_ok", 0)
    if ok == n:
        return (f"{n} certificate(s), all verified", None)
    bad = [r for r in d.get("results") or [] if not r.get("ok")]
    first = bad[0] if bad else {}
    why = (first.get("reasons") or [first.get("unreadable", "")])[0] if first else ""
    return (f"{ok}/{n} verified; {os.path.basename(first.get('path', '?'))}: {why}"[:200], None)


REGISTRY: List[Constituent] = [
    Constituent(
        name="signoff-cert", binary="signoff-cert",
        scope="each certificate is well-formed, its bound is present, and its scope is declared",
        detect=_detect_certs,
        invoke=lambda root, s: ["signoff-cert", "verify", *s.paths, "--json"],
        summarise=_sum_signoff,
        install_hint="pip install git+https://github.com/nickharris808/signoff-cert"),
    Constituent(
        name="honestbench", binary="honestbench",
        scope="every file the manifest lists is present and hashes to what it claimed",
        detect=_detect_manifest,
        # `honestbench verify` takes TWO POSITIONALS, manifest first: `verify <manifest> <dir>`.
        # This used to pass `<dir> --manifest <m>`, so argparse rejected it and the leg's
        # "detail" was the usage message. It reported UNVERIFIED rather than a pass -- the
        # discipline held -- but the check had never once run. Caught by executing the tutorial
        # rather than by reading the code; there is now a test that runs every constituent's
        # invocation against a real fixture and fails on a usage error.
        invoke=lambda root, s: ["honestbench", "verify", s.paths[0],
                                os.path.dirname(s.paths[0]) or "."],
        install_hint="pip install git+https://github.com/nickharris808/honestbench"),
    Constituent(
        name="sf-verify", binary="sf-verify",
        scope="the log's hash chain is intact — NOT that the log is complete",
        detect=_detect_chainlog,
        invoke=lambda root, s: ["sf-verify", "chain", s.paths[0], "--json"],
        install_hint="pip install git+https://github.com/nickharris808/sf-verify"),
    Constituent(
        name="gridlock", binary="gridlock",
        scope="the imported lock-order graph has no cycle — a partial graph, see its scope note",
        detect=_detect_wait_graph,
        # TWO stages, deliberately. `import` alone exits 0 on a successful import, which says
        # nothing at all about deadlock; the verdict is `check`'s. Running only the first stage
        # and reporting its exit code was a real defect here, caught on the first live tree.
        invoke=lambda root, s: [["gridlock", "import", "python", root],
                                ["gridlock", "check", "-", "--json"]],
        summarise=_sum_gridlock,
        install_hint="pip install git+https://github.com/nickharris808/gridlock"),
    Constituent(
        name="proof-drift", binary="proof-drift",
        scope="constants in the Lean sources still match the runtime code bound to them",
        detect=_detect_lean,
        invoke=lambda root, s: ["proof-drift", "source", root],
        install_hint="pip install git+https://github.com/nickharris808/proof-to-code-drift"),
]

#: Tools deliberately NOT auto-run, with the reason. Printed on request so the exclusion is
#: visible rather than implicit — a reader should be able to see the whole portfolio and why
#: only part of it applies to a static tree.
NOT_AUTOMATABLE = {
    "kvleak": "needs a live inference endpoint and a tenant pair; a repository has neither",
    "kvprobe": "needs a live provider endpoint and a budget for probe calls",
    "tokencount": "needs a claimed count to check a claim against; nothing in a tree asserts one",
    "illusion-bench": "is a benchmark you run against YOUR oracle, not a property of this tree",
    "kv-reuse-econ-bench": "reproduces a published figure; it is not an audit of your repository",
    "llm-tenant-isolation-bench": "reproduces published isolation numbers, same reason",
    "formal-proof-mcp": "is a server for an agent to call, not a check with a verdict",
}

__all__ = ["Constituent", "Subject", "REGISTRY", "NOT_AUTOMATABLE", "walk", "MAX_FILES"]
