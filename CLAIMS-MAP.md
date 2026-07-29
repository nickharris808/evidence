# CLAIMS-MAP — evidence

**Tag: CLEAN. Licence: Apache-2.0.**

This file exists so the CLEAN tag is *auditable* rather than asserted.

## The line

Every independent claim in the corresponding filed specification terminates in a **physical
actuation** step — admitting or refusing an operation and thereby granting or withholding a
physical resource.

`evidence` runs checkers and prints an aggregate. It grants and withholds nothing.

## Claims approached, and the step not performed

| Filed claim family | What it recites | What evidence does instead |
|---|---|---|
| Proof-carrying admission | obtain evidence, evaluate it against a policy, **and admit or refuse an operation accordingly** | Obtains verdicts from constituent tools and evaluates them under an aggregation rule. Stops there: the aggregate is printed and returned as an exit code. Nothing is admitted, refused, provisioned, or actuated. |
| Composed evidence with a propagated bound | combining multiple evidentiary legs such that the composite assurance does not exceed the weakest constituent, **and gating on the composite** | The propagation is implemented and tested (`verdict.aggregate`). The gate is not: `evidence` has no admission point, no resource, and no caller whose operation it can refuse. |

## An important non-claim

An exit code is not an actuation. `evidence audit` returning 1 does not stop a build — a CI
configuration might choose to, and that choice, along with the actuation it performs, belongs
entirely to the user's pipeline. The distinction is the same one every package in this portfolio
draws: **reporting a verdict is measurement; acting on it is the gate.**

## What would cross the line

Adding a mode that blocks a merge, refuses a deployment, withholds a credential, or gates
admission of any operation on the aggregate verdict. None exists, and the measure-only rail
(`oss/tools/check_measure_only.py`) fails the build if one appears.
