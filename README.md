# evidence

**Run the verification portfolio over your repository and get one answer — the weakest leg, never the mean.**

[![tests](https://github.com/nickharris808/evidence/actions/workflows/tests.yml/badge.svg)](https://github.com/nickharris808/evidence/actions/workflows/tests.yml)
[![licence](https://img.shields.io/badge/licence-Apache--2.0-blue.svg)](LICENSE)

Twelve tools that each answer one question well are twelve things to run and twelve results to
reconcile. `evidence` detects which of them can say anything about your tree, runs those, and
combines the results under one rule:

> **The aggregate is the weakest leg, never the mean.**

Four checks that passed and one that could not run is not *80% verified*. It is **unverified**,
with four things known about it.

## Install

```bash
pip install evidence-runner                 # the runner alone
```

> ⚠️ **`pip install "evidence-runner[all]"` DOES NOT WORK, and it is still in the copy on PyPI.**
> That extra names five constituents — `gridlock-certify`, `signoff-cert`, `honestbench`,
> `sf-verify`, `proof-to-code-drift` — and **none of the five is on PyPI**, so pip stops with
> `No matching distribution found for gridlock-certify`. The runner itself installs fine; only the
> extra fails. The extra is removed here and the fix reaches PyPI at the next release; version
> 0.1.0, live now, still carries it.

The constituents are installed from their repositories until those names are published:

```bash
pip install \
  "gridlock-certify    @ git+https://github.com/nickharris808/gridlock@v0.1.0" \
  "signoff-cert        @ git+https://github.com/nickharris808/signoff-cert@v1.0.1" \
  "honestbench         @ git+https://github.com/nickharris808/honestbench@v0.2.0" \
  "sf-verify           @ git+https://github.com/nickharris808/sf-verify@v0.1.0" \
  "proof-to-code-drift @ git+https://github.com/nickharris808/proof-to-code-drift@v0.1.0"
```

> **Install name vs import name.** The distribution is `evidence-runner`; the module you import is
> `evidence`. The bare name `evidence` on PyPI belongs to an unrelated project (a DFXML
> differential-analysis tool) — installing it will not give you this tool. If you happen to have
> both installed, they provide modules of the same name and will shadow each other; install only
> one.

`evidence` works without any constituent installed — each missing tool reports `MISSING` and
does not vote. It cannot drag the verdict down, and it cannot hold it up either.

## 30-second quickstart

```bash
evidence audit .                     # the human report
evidence audit . --format sarif      # GitHub code scanning
evidence audit . --format junit      # any CI's test view
evidence tools                       # what can run, and what deliberately cannot
```

Exit codes are the portfolio dialect: **0** checked and holds · **1** checked and fails ·
**2** NOT checked.

## Worked example — a real lock-order inversion

Two locks taken in opposite orders in two functions. Save as `src/pool.py`:

```python
import threading
conn_lock = threading.Lock()
stats_lock = threading.Lock()

def checkout():
    with conn_lock:
        with stats_lock:
            pass

def report():
    with stats_lock:
        with conn_lock:
            pass
```

```console
$ evidence audit .
  gridlock       WEDGES: conn_lock -> stats_lock -> conn_lock   [FAIL]
  honestbench    no evidence manifest found (honestbench n...   [n/a]
  proof-drift    no Lean sources, so there is no proof to ...   [n/a]
  sf-verify      no hash-chained decision log (.jsonl with...   [n/a]
  signoff-cert   no signoff-cert/v1 certificates found          [n/a]
  --------------------------------------------------------------------------
  AGGREGATE: FAILED — 1 fail, 4 n/a
  gridlock is FAILED, and the aggregate is the weakest leg — 0 other constituent(s) passing does not lift it
  The aggregate is the WEAKEST leg, never the mean.

  This does NOT prove:
    - that the constituents cover everything worth checking — an audit is exactly as broad as the tools that ran, and a PASSED aggregate over two legs is a narrow statement
    - that a NOT_APPLICABLE leg found nothing wrong; it looked for nothing, which is different
    - anything a constituent's own scope section disclaims — this aggregate inherits every limit of every leg it summarises, and adds no confidence of its own
$ echo $?
1
```

Reproduce it exactly: install the runner and its constituents with the two commands under
**Install** above, save the file above, run the command. (Not `evidence-runner[all]` — that
extra does not resolve; see the warning there.)

## The verdict algebra

Weakest to strongest, and `min` over this ordering *is* the aggregation rule:

| verdict | means | exit |
|---|---|---:|
| `FAILED` | a check ran and the property does not hold | 1 |
| `UNVERIFIED` | a check could not be completed; nothing is known | 2 |
| `PASSED` | a check ran and the property holds | 0 |

`FAILED` is weakest because it is the only value reporting a known defect. `UNVERIFIED` sits above
it — "we don't know" beats "we know it's broken" — but strictly below `PASSED`, and **no number of
passes can lift it.**

Two values sit outside the algebra and do not vote:

- **`n/a`** — the tool found nothing here to speak about. Folding this in as an abstention would
  make every repository permanently `UNVERIFIED`, and a warning nobody can ever clear is a warning
  everybody learns to ignore.
- **`MISSING`** — the tool is not installed. Loud rather than skipped, because an aggregate
  assembled from whichever tools happened to be importable is an aggregate whose scope depends on
  the machine that ran it.

**But an aggregate over zero checks is `UNVERIFIED`, always.** `all([])` is `True`, and a runner
that reports PASS because nothing objected is the exact bug this portfolio exists to prevent,
reappearing one level up. There is a test for it.

## What runs, and what deliberately does not

```console
$ evidence tools
Constituents this audit can run:

  gridlock       the imported lock-order graph has no cycle — a partial graph, see its scope note
  honestbench    every file the manifest lists is present and hashes to what it claimed
  proof-drift    constants in the Lean sources still match the runtime code bound to them
  sf-verify      the log's hash chain is intact — NOT that the log is complete
  signoff-cert   each certificate is well-formed, its bound is present, and its scope is declared

Deliberately NOT auto-run, and why:

  formal-proof-mcp             is a server for an agent to call, not a check with a verdict
  illusion-bench               is a benchmark you run against YOUR oracle, not a property of this tree
  kv-reuse-econ-bench          reproduces a published figure; it is not an audit of your repository
  kvleak                       needs a live inference endpoint and a tenant pair; a repository has neither
  kvprobe                      needs a live provider endpoint and a budget for probe calls
  llm-tenant-isolation-bench   reproduces published isolation numbers, same reason
  tokencount                   needs a claimed count to check a claim against; nothing in a tree asserts one
```

The exclusions are printed rather than implied. A reader should be able to see the whole portfolio
and why only part of it applies to a static tree.

## CI

```yaml
- run: pip install evidence-runner
  # The constituents are not on PyPI yet, so they install from their repositories. Pinned to
  # tags: a CI step that tracks a branch is not reproducible. Drop any line you do not want
  # to run -- a missing tool reports MISSING and does not vote, it does not fail the audit.
- run: |
    pip install \
      "gridlock-certify    @ git+https://github.com/nickharris808/gridlock@v0.1.0" \
      "signoff-cert        @ git+https://github.com/nickharris808/signoff-cert@v1.0.1" \
      "honestbench         @ git+https://github.com/nickharris808/honestbench@v0.2.0" \
      "sf-verify           @ git+https://github.com/nickharris808/sf-verify@v0.1.0" \
      "proof-to-code-drift @ git+https://github.com/nickharris808/proof-to-code-drift@v0.1.0"
- run: evidence audit . --format sarif > evidence.sarif
  continue-on-error: true
- uses: github/codeql-action/upload-sarif@v3
  with: { sarif_file: evidence.sarif }
```

A passing leg is emitted at `note` level rather than omitted, because a SARIF file with no results
is indistinguishable from a run that checked nothing. In JUnit an `UNVERIFIED` leg is an
`<error>`, never a `<skipped>` — a skipped test is one nobody wanted to run; an unverified check is
one that was wanted and could not be completed, and dashboards colour those very differently.

## Library use

```python
from evidence import audit, render, to_sarif

agg = audit(".")
print(agg.verdict, agg.exit_code, agg.weakest)
print(render(agg))
open("evidence.sarif", "w").write(to_sarif(agg))
```

## Honest scope — what a PASSED here proves, and what it does not

A `PASSED` aggregate says: *every constituent that had something to check, checked it and found
the property held.* It does **not** say:

- **that the constituents cover everything worth checking.** An audit is exactly as broad as the
  tools that ran. A `PASSED` over two legs is a narrow statement, which is why coverage is printed
  next to the verdict rather than in a footnote.
- **that an `n/a` leg found nothing wrong.** It looked for nothing. Those are different, and the
  difference is the entire reason `n/a` is not folded into the verdict.
- **anything a constituent's own scope section disclaims.** This aggregate inherits every limit of
  every leg it summarises and adds no confidence of its own. `gridlock`'s Python importer cannot
  see locks across function boundaries; `sf-verify` checks that a chain is intact, not that a log
  is complete. Those limits survive aggregation intact.

Detection is deliberately conservative. Where a tool needs an argument this package cannot infer —
a live endpoint, a tokenizer, a claimed count — the constituent reports `n/a` and says what it
would have needed, rather than guessing at a subject and producing a confident verdict about the
wrong thing.

## What this does not do

`evidence` **measures**. It runs checkers and reports. It never admits, refuses, provisions or
actuates anything, and it has no code path that could. See [CLAIMS-MAP.md](CLAIMS-MAP.md).

## Development

```bash
pip install -e ".[dev]"
python -m pytest -q          # 46 tests
```

## License

Apache-2.0. See [LICENSE](LICENSE) and [CONTRIBUTING.md](CONTRIBUTING.md).

**Citing this?** Metadata is in [CITATION.cff](CITATION.cff) — GitHub's "Cite this repository" button reads it directly.

<!-- PORTFOLIO -->
---

## The rest of the portfolio

25 artifacts, one idea: **a measurement you cannot check is a press release.** Every tool
here reports; none of them gates.

**Tools**

| | |
|---|---|
| [`abstain-bench`](https://github.com/nickharris808/abstain-bench) | how often does a verifier pass input it could not check? |
| [`evidence`](https://github.com/nickharris808/evidence) | run the whole portfolio over your repo — the weakest leg, never the mean ← you are here |
| [`floorgen`](https://github.com/nickharris808/floorgen) | what must your system remember? an exact lower bound |
| [`formal-proof-mcp`](https://github.com/nickharris808/formal-proof-mcp) | a proof kernel for your coding agent |
| [`gatecount`](https://github.com/nickharris808/gatecount) | exactly how many states does removing this check admit? |
| [`gridlock`](https://github.com/nickharris808/gridlock) | certify a wait-for relation cannot wedge |
| [`honestbench`](https://github.com/nickharris808/honestbench) | measure your CI's escape rate |
| [`kvleak`](https://github.com/nickharris808/kvleak) | cross-tenant leak scanner |
| [`kvprobe`](https://github.com/nickharris808/kvprobe) | model-substitution detector with a measured FPR |
| [`preregister`](https://github.com/nickharris808/preregister) | refuses to seal a plan whose conclusion is already fixed |
| [`proof-carrying-ci`](https://github.com/nickharris808/proof-carrying-ci) | the whole portfolio as one CI check, with SARIF |
| [`proof-to-code-drift`](https://github.com/nickharris808/proof-to-code-drift) | fail the build when the proof stops matching |
| [`sf-verify`](https://github.com/nickharris808/sf-verify) | re-derive admission decisions offline |
| [`signoff-cert`](https://github.com/nickharris808/signoff-cert) | certificates that carry their own false-pass bound |
| [`tokencount`](https://github.com/nickharris808/tokencount) | a token count both parties can recompute |

**Benchmarks** — each recomputes one of our own published numbers from its certificate

| | |
|---|---|
| [`illusion-bench`](https://github.com/nickharris808/illusion-bench) | how many broken kernels does your oracle admit? |
| [`kv-reuse-econ-bench`](https://github.com/nickharris808/kv-reuse-econ-bench) | recompute our economics headline |
| [`llm-tenant-isolation-bench`](https://github.com/nickharris808/llm-tenant-isolation-bench) | recompute our isolation figures |

**Datasets**

| | |
|---|---|
| [`abstain-corpus`](https://huggingface.co/datasets/nickh007/abstain-corpus) | 32 inputs a verifier must NOT pass |
| [`kv-reuse-econ-traces`](https://huggingface.co/datasets/nickh007/kv-reuse-econ-traces) | per-workload reuse accounting + the closed form |
| [`kv-tenant-isolation-bench`](https://huggingface.co/datasets/nickh007/kv-tenant-isolation-bench) | isolation observations, uninterpretable rows included |
| [`llm-precision-fingerprints`](https://huggingface.co/datasets/nickh007/llm-precision-fingerprints) | precision-labelled logprobs with a negative control |

**Try it in a browser** — no install, no GPU

| | |
|---|---|
| [`negative-results-atlas`](https://huggingface.co/spaces/nickh007/negative-results-atlas) | ten claims we took back |
| [`tenant-leak-demo`](https://huggingface.co/spaces/nickh007/tenant-leak-demo) | the residency calculator |
| [`wait-for-visualiser`](https://huggingface.co/spaces/nickh007/wait-for-visualiser) | paste a wait-for graph, see the cycle |

### Documentation

Everything above, explained in one place: **<https://nickharris808.github.io/evidence-docs/>** —
the [tutorial](https://nickharris808.github.io/evidence-docs/start/tutorial/),
[what this proves and what it does not](https://nickharris808.github.io/evidence-docs/concepts/what-this-proves/),
and a [CLI reference](https://nickharris808.github.io/evidence-docs/reference/cli/) generated by
running `--help` on every published command.

### The commercial edition

Everything above is **measure-only** and Apache-2.0: it tells you what is true and never acts on
it. The **enforcement** side — binding a partition key at the admission decision, the compiled gate
corpus, and the certificate-*issuing* faucet — is covered by filed patents and licensed separately.

**Reading is free. Enforcing is licensed.**
<!-- /PORTFOLIO -->
