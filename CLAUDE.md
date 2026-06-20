# A Language Built on Differential Logical Relations & Program Metrics — Project Primer

## Motivation

Two practical problems in industrial programming both reduce, at their core, to the same
question: *if the input to a program changes by some amount, how much does the output
change?*

- **Differential privacy / sensitive data analytics**: you need a provable upper bound on
  how much a query's output can change when one record in the input is added, removed, or
  modified. Get this wrong and your privacy guarantee is fiction.
- **Incremental / reactive computation**: build systems, materialized views, streaming
  aggregates, reactive UIs — all need to take a small change to the input and produce the
  corresponding change to the output *without rerunning the whole computation*, and get it
  exactly right, not approximately right.

Existing tools solve these separately, with type systems that are weaker than they need to
be. The goal of this project is a single language, grounded in Ugo Dal Lago's research
program on differential logical relations and program metrics, where "how output-change
depends on input-change" is a first-class part of the type system — precise enough to
serve as the foundation for *both* problems, and in fact to unify them into something
neither existing line of work does on its own: incrementally-updated, privacy-budget-aware
streaming analytics.

## Literature Review

### Core theory: Differential Logical Relations & Program Metrics (Dal Lago et al.)

- **Dal Lago, Gavazzo, Yoshimizu — "Differential Logical Relations, Part I: The
  Simply-Typed Case"** (ICALP 2019; long version arXiv:1904.12137). Introduces DLR: instead
  of measuring the distance between two programs with a single number, measure it with an
  object that reflects the *type* (interactive complexity) of the programs being compared.
  At function type, the "distance" between two functions is itself a function — relating
  errors in input to errors in output — not a flattened scalar bound. Shows ordinary
  logical relations (boolean equivalence) and classic numeric program metrics are both
  special cases of this more general notion. Organizes DLR in a cartesian closed category
  (notably, plain metric relations don't have this structure — only monoidal closed).

- **Dal Lago, Gavazzo — "Differential Logical Relations, Part II: Increments and
  Derivatives"** (TCS 2021). The practically critical follow-up: a program's "derivative" is
  its canonical self-distance, and this gives a semantic foundation for incremental
  computation — connects differential program semantics directly to incremental computing.

- **Dal Lago, Hoshino, Pistone — "On the Lattice of Program Metrics"** (FSCD 2023,
  arXiv:2302.05022). Studies how the various notions of program metric relate: metrics from
  interpretation in metric spaces, observational/context-distance metrics, equational
  metrics, and a new "interactive metric" built via the Int-construction. Establishes when
  one refines another — the metric analogue of the classical lattice of program
  equivalences.

- **Dal Lago, Hoshino, Pistone — "On the Metric Nature of (Differential) Logical
  Relations"** (FSCD 2025). Clarifies exactly what kind of metric space DLR distances form:
  not a standard (quasi-)metric, but a new structure they call *quasi-quasi-metrics*.
  Useful as a guide for what compositional reasoning principles are actually sound.

- **Crubillé, Dal Lago — "Metric Reasoning About λ-Terms"** (affine case, LICS 2015;
  general case, ESOP 2017). Earlier groundwork: context-distance (the metric analogue of
  Morris-style context equivalence) for probabilistic λ-calculi.

- **Dal Lago, Gavazzo — "A Relational Theory of Effects and Coeffects"** (POPL 2022). The
  unifying layer: graded modal types `□ₛA` where grades `s` come from a semiring-like
  resource algebra, generalizing sensitivity (Reed & Pierce), resource consumption (Orchard
  et al.), and security/information-flow levels as instances of one grading discipline.
  This is the natural type-system scaffold for embedding DLR-style distances.

### The Fuzz family — sensitivity types for differential privacy (the existing industrial-adjacent precedent)

- **Reed, Pierce — Fuzz** (ICFP 2010). First use of linear types for sensitivity: function
  type `A ⊸ₛ B` carries a Lipschitz bound `s`, with soundness theorem
  `d(f x, f y) ≤ s · d(x, y)`. Combined with a probability monad for DP noise mechanisms.
- **Gaboardi et al. — DFuzz** ("Linear Dependent Types for Differential Privacy," POPL
  2013). Extends Fuzz with lightweight dependent types so sensitivity bounds can depend on
  runtime values, not just be static constants.
- **Near et al. — Duet** (2019). Two mutually-defined languages (one for sensitivity, one
  for privacy), supporting more advanced DP variants (approximate / (ε,δ)-DP) and richer
  higher-order programming.
- **Toro et al. — Jazz**, and others (Fuzzi, Solo, Contextual Linear Types for DP). All
  documented limitation: each product/sum type forces an *approximation* in the sensitivity
  analysis, because the type system only carries a single worst-case (global) scalar bound.
  None of these have an incremental-computation story.

### Incremental computation — change structures and derivatives (the engineering precedent for "Part II")

- **Cai, Giarrusso, Rendel, Ostermann — "A Theory of Changes for Higher-Order Languages:
  Incrementalizing λ-Calculi by Static Differentiation"** (PLDI 2014). Defines *change
  structures*: for each type, a set of changes with operations `⊕` (apply a change) and `⊖`
  (compute the change between two values). Gives a fully static, automatic program
  transformation from a function to its derivative — a function from input-changes to
  output-changes — with a machine-checked (Agda) correctness proof.
- **Giarrusso et al. — "Incremental λ-Calculus in Cache-Transfer Style"** (ESOP 2019).
  Refines derivatives to be *self-maintainable* (don't need to inspect the base input, only
  the change) by threading cached intermediate results — necessary for derivatives to
  actually be cheap, not just correct.
- **Alvarez-Picallo, Ong — "Change Actions: Models of Generalised Differentiation"**.
  Generalizes change structures to *change actions* over arbitrary cartesian categories;
  connects to cartesian differential categories and (per Kelly, Pearlmutter, Siskind) to
  automatic differentiation.

### The unifying observation

- **Pistone — "From Identity to Difference: A Quantitative Interpretation of the Identity
  Type"** (arXiv:2107.06150). Builds "difference type theory" (dTT) explicitly to show that
  approximate equivalence, metric preservation, incremental computing, automatic
  differentiation, and differential privacy all share one structure: every program has a
  derivative relating input-errors/changes to output-errors/changes; a *bounded* derivative
  gives you a sensitivity/privacy guarantee, an *exact* derivative gives you incremental
  computation. This is the clearest existing confirmation that the project's premise — one
  language serving both DP and incremental computation — is not a stretch, it's the same
  mathematical object specialized two ways.

## Design Direction

**Core idea**: one linear/affine core calculus with graded function types `A —[g]→ B`,
where `g` carries an actual DLR-style relational interpretation (a map from an input
relation to an output relation) rather than a bare numeric bound. Two grade algebras are
provided as instances:

- `Sens` — a sensitivity quantale, indexed/dependent in the style of DFuzz so that bounds
  can vary by input region (local sensitivity) instead of collapsing to one global
  Lipschitz constant. This is the direct fix for the precision loss that the entire Fuzz
  lineage documents at product/sum types.
- `Δ` — a change-action algebra (Cai et al. / Alvarez-Picallo & Ong) giving real `⊕`/`⊖`
  and a derivative, carrying the ILC correctness theorem: running the derivative and
  patching equals rerunning on the patched input.

Effects (notably DP noise mechanisms) are integrated via the effect/coeffect relational
theory so that randomized mechanisms compose soundly with both grades.

**The unique opportunity**: incrementally-maintained, privacy-budget-tracked streaming
analytics — private materialized views that update cheaply as records stream in, where the
privacy cost of each incremental update (not just a one-shot batch query) is type-tracked.
This is a continual-observation differential privacy problem, and it is itself a
coeffect-counting problem (how much budget has this stream consumed so far) — which is
exactly what the graded/coeffect structure is for. Neither the Fuzz family nor the ILC
family addresses this; it's the genuine differentiator.

## Build Plan

**v0 — typed EDSL, fastest path to something runnable.**
Host in Haskell or OCaml (not a standalone compiler yet). Implement a small combinator
library — `map`, `filter`, `groupBySum`, `join` — each shipped with both a sensitivity
grade and a derivative, discharging two soundness obligations per combinator:
1. Sensitivity theorem: typing implies `d(out, out') ≤ g · d(in, in')`.
2. Derivative correctness: typing implies `f(a ⊕ δa) == f(a) ⊕ df(a, δa)`.

Add a Laplace-noise mechanism as the privacy-consuming primitive, composed through the
grades so total epsilon budget is tracked across a pipeline.

**Demo target**: a streaming dashboard (e.g. daily-active-users over an event stream) that
updates incrementally per event instead of recomputing from scratch, with a
compile-time-checked privacy budget that accounts for repeated incremental updates.

**v1 — standalone core calculus**, if v0 validates the approach. Bidirectional type
checker, SMT-assisted constraint solving for the grade arithmetic (following μFuzz's
approach of offloading nonlinear sensitivity constraints to a solver), since a host
language's native type system won't cleanly carry the full grade algebra.

## Open Questions / Design Risks

- How much of DLR's full categorical generality is actually needed for the two target
  grade algebras, versus how much can be a simpler graded-coeffect system in the Granule
  lineage with DLR only informing the *soundness proofs*, not the surface type theory?
- Local/data-dependent sensitivity (the `Sens` fix) likely needs some form of dependent or
  index types (à la DFuzz) — how much dependent-type machinery is tolerable before it hurts
  adoption?
- Continual-observation DP composition theorems (how privacy budget degrades over repeated
  incremental updates) are an active research area in their own right (cf. binary
  mechanism / tree-based aggregation literature) — the type system needs to encode a
  *correct* composition theorem, not an ad hoc one.
- Self-maintainability (Cache-Transfer Style) adds real implementation complexity; decide
  whether v0 needs it or can ship with plain (correct but not always cheap) derivatives
  first.

## References (for follow-up reading)

- Dal Lago, Gavazzo, Yoshimizu. Differential Logical Relations, Part I. ICALP 2019.
- Dal Lago, Gavazzo. Differential Logical Relations, Part II. TCS 2021.
- Dal Lago, Hoshino, Pistone. On the Lattice of Program Metrics. FSCD 2023.
- Dal Lago, Hoshino, Pistone. On the Metric Nature of (Differential) Logical Relations. FSCD 2025.
- Crubillé, Dal Lago. Metric Reasoning About λ-Terms (affine: LICS 2015; general: ESOP 2017).
- Dal Lago, Gavazzo. A Relational Theory of Effects and Coeffects. POPL 2022.
- Reed, Pierce. Fuzz. ICFP 2010.
- Gaboardi, Haeberlen, Hsu, Narayan, Pierce. DFuzz / Linear Dependent Types for Differential Privacy. POPL 2013.
- Near et al. Duet. 2019.
- Orchard, Liepelt, Eades III. Quantitative Program Reasoning with Graded Modal Types (Granule). ICFP 2019.
- Cai, Giarrusso, Rendel, Ostermann. A Theory of Changes for Higher-Order Languages. PLDI 2014.
- Giarrusso et al. Incremental λ-Calculus in Cache-Transfer Style. ESOP 2019.
- Alvarez-Picallo, Ong. Change Actions: Models of Generalised Differentiation.
- Pistone. From Identity to Difference: A Quantitative Interpretation of the Identity Type. arXiv:2107.06150.
