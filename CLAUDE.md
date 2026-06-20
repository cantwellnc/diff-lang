# Program Distance for Software Engineering & LLM Code-Gen Guidance — Project Primer

*(Supersedes the earlier DP-and-incremental-computing draft. See "Why not differential
privacy" below for the reasoning.)*

## Motivation

Tools that need to know "how much did this code's behavior actually change" currently
measure something else entirely: syntactic tree-edit distance, n-gram overlap (CodeBLEU),
or embedding cosine similarity. These are proxies for semantic distance, not the thing
itself, and the gap shows up concretely: a 2026 study of LLM-based test generation under
code evolution found that under semantics-preserving edits, generated tests degrade sharply
and the models show "sensitivity to lexical changes rather than true semantic impact" —
current tooling cannot reliably tell "this refactor changed nothing observable" from "this
refactor silently broke a corner case."

There is an existing, fairly mature field that *does* reason about real program semantics
for exactly this purpose — regression verification and semantic differencing, via symbolic
execution and abstract interpretation (SymDiff, differential symbolic execution, abstract
semantic differencing). But it has a structural ceiling: it mostly answers a boolean
question (equivalent / not-equivalent), and where it can't decide, it says "unknown" and
stops. A recent tool in this line (PASDA) explicitly names this as the open problem —
existing approaches that can't prove equivalence or non-equivalence "provide no information
regarding the programs' non-/equivalence."

This is precisely the upgrade differential logical relations (DLR) were built to make to
ordinary logical relations: instead of a boolean (related / not related), a structured,
type-respecting *quantity* — and for function types, that quantity is itself a function
relating input-difference to output-difference, not a collapsed worst-case number. Applied
here: instead of "equivalent / not-equivalent / unknown," you get "identical except when the
input satisfies condition X, in which case the output differs by at most Y" — a genuinely
more useful answer for code review risk-scoping, regression test selection, and gating
LLM-generated patches against a reference behavior.

Incremental computation rides along as a secondary application of the same machinery: Dal
Lago & Gavazzo's "Part II" result is that a program's *derivative* — an exact (not just
bounded) version of this same distance-relating object — is the right semantic foundation
for incremental re-execution. So the same core, when it can compute an exact rather than
merely bounded relation, can also drive cheap incremental re-runs of dataflow/pipeline-style
code after a small edit. This is not the product's main pitch — it's a capability that falls
out for free when the underlying program happens to be amenable to it.

## Literature Review

### Core theory: Differential Logical Relations & Program Metrics (Dal Lago et al.)

- **Dal Lago, Gavazzo, Yoshimizu — "Differential Logical Relations, Part I: The
  Simply-Typed Case"** (ICALP 2019; arXiv:1904.12137). The foundational move: measure
  program distance with a type-respecting object, not a number. At function type, the
  distance between two functions is itself a function relating input-difference to
  output-difference. Ordinary logical relations (boolean equivalence) and classic numeric
  program metrics are both special cases.
- **Dal Lago, Gavazzo — "Differential Logical Relations, Part II: Increments and
  Derivatives"** (TCS 2021). A program's derivative is its canonical self-distance —
  the semantic link to incremental computation (the secondary application here).
- **Dal Lago, Gavazzo — "Effectful Program Distancing"** (POPL 2022). Extends program
  distancing to *effectful* programs — directly relevant, since almost no real code is
  pure; this is the theoretical backbone for handling I/O, exceptions, and mutation in the
  core IR rather than restricting to a toy pure subset.
- **Dal Lago, Hoshino, Pistone — "On the Lattice of Program Metrics"** (FSCD 2023,
  arXiv:2302.05022). How the various notions of program metric (denotational,
  observational/context-distance, equational, interactive) refine one another — useful as
  a map of which notion of "distance" is appropriate for which guarantee we want to give
  downstream (e.g., a sound static bound vs. an exact dynamic derivative).
- **Dal Lago, Hoshino, Pistone — "On the Metric Nature of (Differential) Logical
  Relations"** (FSCD 2025). What kind of metric space DLR distances actually form
  (quasi-quasi-metrics) — informs which compositional reasoning principles (e.g., triangle
  inequality across a chain of patches) are actually sound to rely on.
- **Crubillé, Dal Lago — "Metric Reasoning About λ-Terms"** (affine: LICS 2015; general:
  ESOP 2017). Context-distance for probabilistic λ-calculi; groundwork for the
  observational notion of metric.

### Adjacent, already-mature field: regression verification & semantic differencing

- **Jackson, Ladd — "Semantic Diff: A Tool for Summarizing the Effects of
  Modifications"** (ICSM 1994). The original framing of the problem this project targets.
- **Lahiri, Hawblitzel, Kawaguchi, Rebêlo — SymDiff** (CAV 2012). Language-agnostic
  semantic diff tool for imperative programs, built on the Boogie intermediate verification
  language, with C/C#/x86 frontends — the precedent for a language-agnostic IR + frontend
  architecture.
- **Person, Dwyer, Elbaum, Păsăreanu — "Differential Symbolic Execution"** (FSE 2008) and
  **Person, Yang, Rungta, Khurshid — "Directed Incremental Symbolic Execution"** (PLDI
  2011). Symbolic-execution-based approaches to characterizing behavioral differences
  between two program versions.
- **Partush, Yahav — "Abstract Semantic Differencing for Numerical Programs"** (SAS 2013)
  and **"... via Speculative Correlation"** (PLDI 2014). Abstract-interpretation-based
  differencing that characterizes *both* changed and unchanged behavior, rather than just
  a single counterexample — closer in spirit to what this project wants, though still
  boolean/region-based rather than quantitative.
- **Godlin, Strichman — "Regression Verification"** (DAC 2009). Establishes the
  problem area: checking behavioral equivalence across versions of an evolving program, as
  distinct from translation validation (where the two programs are at different abstraction
  levels, e.g. source vs. compiled).
- **A 2025 partition-based tool (PASDA)** reports that this field's existing approaches,
  when they cannot prove equivalence or non-equivalence, return "unknown" with no further
  information — the gap this project is aimed at closing with a quantitative, structured
  answer instead.

### LLM code-gen — current (weak) proxies for code similarity, and the documented gap

- **TSED (Tree Similarity of Edit Distance)**, used e.g. in recent prompt-sensitivity
  studies of code LLMs: an openly-available syntax-tree edit-distance metric, explicitly
  *not* claiming semantic equivalence.
- **CodeBLEU**, used in ensemble/voting approaches to LLM code generation (e.g. EnsLLM):
  n-gram-style lexical overlap adapted for code, combined in practice with an
  execution-based differential analysis (via the property-based testing tool CrossHair) as
  a complementary, sampling-based behavioral check — i.e., practitioners already reach for
  differential testing because the static syntactic metric isn't enough, but rely on
  sampled counterexamples rather than a compositional, typed guarantee.
- **"Evaluating LLM-Based Test Generation Under Software Evolution"** (2026,
  arXiv:2603.23443) — direct evidence of the problem: under semantics-preserving edits, LLM-
  generated regression tests degrade sharply, with the paper concluding current test
  generation "relies heavily on surface-level cues" rather than tracking real behavioral
  impact.

### Incremental computation (secondary application — same derivative machinery, applied to execution rather than analysis)

- **Cai, Giarrusso, Rendel, Ostermann — "A Theory of Changes for Higher-Order
  Languages"** (PLDI 2014). Change structures (`⊕`/`⊖`) and a static program-to-derivative
  transformation with a machine-checked correctness proof.
- **Giarrusso et al. — "Incremental λ-Calculus in Cache-Transfer Style"** (ESOP 2019).
  Makes derivatives *self-maintainable* (cheap to run without recomputing the base value).
- **Alvarez-Picallo, Ong — "Change Actions: Models of Generalised Differentiation."**
  Categorical generalization connecting to cartesian differential categories and automatic
  differentiation.
- **Pistone — "From Identity to Difference"** (arXiv:2107.06150). Explicit unification:
  approximate equivalence, incremental computing, automatic differentiation, and
  differential-privacy-style metric preservation are all the same derivative idea,
  specialized differently (bounded vs. exact).

### Why not differential privacy (dropped from this plan)

Considered and deprioritized. The DP tools actually running in production — Tumult
Analytics (US Census Bureau, IRS, Wikimedia), Google's PipelineDP, IBM's diffprivlib,
OpenDP — are Python libraries deliberately designed to mimic pandas/Spark APIs for
non-experts. A usability study comparing these four found completion rates tracked with how
familiar the API felt, and the tool least tied to a familiar API (OpenDP) had the worst
completion rates. The Fuzz/DFuzz/Duet lineage of sensitivity-typed languages is fifteen
years old with essentially no production adoption. The market has converged on "library
with familiar API and expert-vetted primitives," which is close to the opposite of "new
linear/graded type system" — so this is left out of the plan rather than forced into it.

## Design Direction

**Core idea**: a small typed intermediate representation (IR) with a formally-defined
DLR-style relation, compositional over the IR's type structure, extended (via the
effectful-program-distancing line of work) to handle I/O, exceptions, and mutation rather
than restricting to a pure subset. This IR is the *specification* of what "distance between
two program versions" precisely means — not something end users write directly.

**Frontend**: translate a real source language into the IR. Start with Python, since it's
both the most common LLM-codegen target and what most of the cited SE literature already
operates on. Mirror SymDiff's language-agnostic-IR-plus-frontends architecture so other
languages can be added later without redesigning the core.

**Approximation engine**: exact DLR distances are uncomputable in general for Turing-complete
code (this is inherent, not a design flaw), so the practical tool computes *sound
over-approximations* — combining bounded symbolic execution (as in differential symbolic
execution / SymDiff) with abstract interpretation (as in Partush & Yahav) — but reports a
structured, region-conditioned, quantitative answer rather than collapsing to
equivalent/not-equivalent/unknown. This quantitative reporting, grounded in the DLR
relational structure, is the actual novel contribution relative to the existing regression-
verification field.

**Outputs / use cases**:
1. Patch impact report: "identical except when input satisfies P; in that region, output
   differs by at most ε" — for code-review risk-scoping.
2. Regression test selection: cross-reference the non-zero-distance region against test
   input coverage to flag tests that must rerun vs. tests provably unaffected.
3. Codegen verification gate: given a reference implementation or spec and an LLM-generated
   candidate, check the candidate's distance from the reference is within tolerance —
   usable as a pre-commit check or as a tool an agentic coding system calls on itself before
   proposing an edit.
4. Bonus, when the engine derives an *exact* rather than merely bounded relation (the
   program is amenable to symbolic differencing in the ILC sense): reuse that exact
   derivative to incrementally re-run dataflow/pipeline-style code after a small edit,
   instead of rerunning from scratch.

## Build Plan

**v0 — smallest useful tool.**
1. Define the core IR and its DLR-style relational semantics (drawing directly on Dal Lago
   et al.'s formal definitions, extended per "Effectful Program Distancing" for basic
   effects).
2. Python frontend for a tractable subset: pure-ish functions, standard control flow, common
   stdlib/collections — expand coverage incrementally rather than aiming for all of Python
   immediately.
3. Approximation engine: bounded symbolic execution + an SMT solver (e.g. Z3) for the core
   equivalence/bound checks, structured to report region-conditioned bounds rather than a
   single boolean.
4. CLI: `distancetool diff old.py new.py --func target_function` → structured impact report
   (region-conditioned distance bound) + a recommended test subset, given an existing test
   suite with known input coverage.
5. Demo: run against a small real Python repo with an existing test suite; compare the
   recommended test subset against naive line-diff-based test selection on a handful of
   real historical commits.

**v1 — codegen-guidance integration.**
Wrap an LLM code-generation call so that `distancetool` checks the candidate against a
reference implementation or spec before the candidate is accepted, demonstrating the
constrained-generation use case end to end (pre-commit gate or agentic-tool-call form).

**v2 — incremental-execution bonus**, only if v0/v1 validate: for programs where the engine
derives an exact rather than bounded relation, wire that derivative into an actual
incremental re-execution path (dataflow/pipeline-shaped code is the natural target), making
the connection to the Cai et al. / ILC line concrete rather than purely theoretical.

## Open Questions / Design Risks

- Precision/scalability tradeoff: which static-analysis backbone (abstract interpretation
  domain, symbolic execution depth/path limits, SMT solver scalability) determines how much
  real-world Python the tool can handle before falling back to "unknown" — need to decide
  acceptable fallback behavior early (e.g., degrade gracefully to a coarser bound rather
  than refusing to answer).
- How much of the IR's type structure should mirror Python's dynamic typing vs. impose a
  simplified static view — too much simplification weakens the guarantees, too much fidelity
  to dynamic typing may make the relational semantics intractable.
- Effects (I/O, mutation, exceptions) are the hard part in practice, not the type-directed
  distance structure itself — "Effectful Program Distancing" is the right theoretical
  starting point, but turning it into a tractable static analysis for real Python is
  genuine, unsolved engineering work.
- How to validate the tool's outputs are actually more useful than the existing
  regression-verification field's boolean/unknown answers — need a concrete benchmark
  (e.g., real historical commits with known regressions) to demonstrate the quantitative,
  region-conditioned answer changes a real decision (which tests to run, whether to approve
  a patch) versus the boolean baseline.

## References (for follow-up reading)

- Dal Lago, Gavazzo, Yoshimizu. Differential Logical Relations, Part I. ICALP 2019.
- Dal Lago, Gavazzo. Differential Logical Relations, Part II. TCS 2021.
- Dal Lago, Gavazzo. Effectful Program Distancing. POPL 2022.
- Dal Lago, Hoshino, Pistone. On the Lattice of Program Metrics. FSCD 2023.
- Dal Lago, Hoshino, Pistone. On the Metric Nature of (Differential) Logical Relations. FSCD 2025.
- Crubillé, Dal Lago. Metric Reasoning About λ-Terms (affine: LICS 2015; general: ESOP 2017).
- Jackson, Ladd. Semantic Diff: A Tool for Summarizing the Effects of Modifications. ICSM 1994.
- Lahiri, Hawblitzel, Kawaguchi, Rebêlo. SymDiff. CAV 2012.
- Person, Dwyer, Elbaum, Păsăreanu. Differential Symbolic Execution. FSE 2008.
- Person, Yang, Rungta, Khurshid. Directed Incremental Symbolic Execution. PLDI 2011.
- Partush, Yahav. Abstract Semantic Differencing for Numerical Programs. SAS 2013; via Speculative Correlation, PLDI 2014.
- Godlin, Strichman. Regression Verification. DAC 2009.
- "Evaluating LLM-Based Test Generation Under Software Evolution." arXiv:2603.23443, 2026.
- "Enhancing LLM Code Generation with Ensembles: A Similarity-Based Selection Approach" (EnsLLM, CodeBLEU + CrossHair differential analysis). arXiv:2503.15838, 2025.
- "Code Roulette: How Prompt Variability Affects LLM Code Generation" (TSED metric). arXiv:2506.10204, 2025.
- Cai, Giarrusso, Rendel, Ostermann. A Theory of Changes for Higher-Order Languages. PLDI 2014.
- Giarrusso et al. Incremental λ-Calculus in Cache-Transfer Style. ESOP 2019.
- Alvarez-Picallo, Ong. Change Actions: Models of Generalised Differentiation.
- Pistone. From Identity to Difference: A Quantitative Interpretation of the Identity Type. arXiv:2107.06150.
