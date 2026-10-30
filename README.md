# alt-invest-agent-evals

A Claude agent that does a private equity associate's first pass on a deal document, and the eval harness that tells you whether it is any good.

Private equity firms receive hundreds of confidential information memorandums (CIMs) a year. Each one is written by the seller's banker to make the company look as good as possible. The first-pass screen decides whether the deal team spends another week on it. Getting that screen wrong is expensive in both directions: chase a bad deal and you burn a team; miss the sentence that kills the deal and you burn a fund.

An LLM can draft that screen in a minute. The hard part is knowing whether to trust it. This repo is mostly about that second part.

## What the agent does

`cimscreen` reads a CIM and returns a structured screen:

- **Financials**: LTM revenue, EBITDA, growth, top-customer share. Null when the document does not state the figure.
- **Red flags**: each with a category and a verbatim quote from the document as evidence.
- **Diligence questions** for management.
- **Recommendation**: pursue, needs more info, or pass.

It is one Claude call with a JSON-schema-constrained output (`output_config.format`). No agent loop, because the task does not need one: the whole document fits in context and there is nothing to look up.

## What the eval measures

The dataset is eight synthetic CIMs (fictional companies, written for this repo) built the way real ones fail diligence: the problem is in the document, but it sits in a qualifying sentence after the headline number.

| Built into the data | What it catches |
|---|---|
| **14 planted red flags**: recurring "non-recurring" add-backs, acquired growth hiding negative organic growth, revenue reported gross of pass-through costs, a patent owned by the CTO personally, a sponsor bank under a consent order | Missing the issue that changes the price |
| **10 decoys**: risks the document raises and then resolves (a hedge, a renewed union contract, a documented seasonal dip, a settled and insured lawsuit) | Crying wolf. An agent that flags everything wastes the deal team's time and scores perfectly on recall alone |
| **1 clean deal** with no planted flags | Same, from the other direction |
| **3 figures the documents never state** | Inventing a plausible number instead of saying it is missing |

Each property is scored separately, never blended into one number:

| Metric | Grader | Why this grader |
|---|---|---|
| Red-flag recall | LLM judge, one yes/no call per planted flag | Matching "the same issue, different words" needs judgment. One question per call keeps it checkable |
| Follow-up question coverage | Same judge call | Did it ask management about the thing it flagged? |
| Decoy false-alarm rate | LLM judge, one call per decoy | Precision, measured directly |
| Evidence grounding | Code: is each quote verbatim in the document? | Hallucinated evidence is the failure that destroys trust; it should never depend on a model's opinion |
| Fact accuracy | Code: numeric match, unit-aware | Deterministic |
| Abstention | Code: null where the document is silent | Kept separate so "returned nothing" never looks like "got it right" |
| Recommendation | Code: in the acceptable set for that case | Several answers can be defensible; the label is a set, not a single value |

## How the harness stays honest

These are the choices that make the numbers mean something. [docs/design.md](docs/design.md) has the reasoning for each.

- **Plumbing failures never become scores.** API errors go to `errors.jsonl`. Truncated, refused and malformed outputs get their own status and are counted, not averaged in as zeros.
- **The served model is checked on every call.** If the API answers with a different model than requested, the run fails loudly.
- **The harness is tested against known answers.** An oracle agent built from the gold labels must score 100%, and a null agent must score near zero. Both run in CI on every push, with no API key.
- **The gold labels are tested against the documents.** Every labelled figure and every evidence quote must actually appear in the CIM it belongs to.
- **The judge is calibrated against hand labels** (`cimeval calibrate-judge`): 13 hand-labelled verdicts including deliberately tricky ones. Examples: naming the topic but not the substance, a decoy that is mentioned only in a question, and a prompt injection hidden in the agent's output. The judge runs on a different model from the agent, so it is not grading its own family's phrasing.
- **Error bars are part of the result.** Reps are averaged within a case, then bootstrapped across cases. With eight cases the intervals are wide, and the report says so instead of hiding it.
- **Regressions are measured paired.** `cimeval compare` diffs two runs case by case and fails CI when a gated metric drops beyond tolerance or its confidence interval is entirely negative. Evidence grounding has a hard floor of 95%.

## Results

First live run, 30 Oct 2026: 8 cases × 2 reps per configuration. The judge (`claude-sonnet-5-5`) agreed with all 13 hand-labelled calibration verdicts. No harness errors, truncations or refusals. Raw rows, configs and reports are in [`results/2026-10-30/`](results/2026-10-30/).

| | Opus 5.5 · prompt v2 | Opus 5.5 · prompt v1 | Haiku 5.5 · low effort · v1 |
|---|---|---|---|
| Red-flag recall | 100% | 100% | 100% |
| Follow-up question coverage | 100% | 100% | 100% |
| **Decoy false-alarm rate** | **12%** (0–38) | **12%** (0–38) | **81%** (62–94) |
| Evidence quotes found verbatim | 100% | 100% | 100% |
| Fact accuracy / abstention | 100% / 100% | 100% / 100% | 100% / 100% |
| Recommendation acceptable | 100% | 100% | 100% |
| Agent cost per screen | $0.035 | $0.033 | $0.001 |
| Latency p50 | 12.7s | 12.8s | 8.1s |

What this shows, including what it does not:

1. **Recall is saturated.** Every configuration found all 14 planted flags, even the smallest model at low effort. In two-page documents the issues are findable by everyone, so the recall metric cannot rank models. The next version needs longer documents and subtler issues: ones that need arithmetic across sections, or that hide in a table footnote.
2. **The decoys do the discriminating.** Haiku also flagged 81% of the resolved non-issues, while Opus flagged 12%. An eval that measured recall alone would have called the two models equal. This is the reason the decoys exist.
3. **The tuned prompt (v2) made no measurable difference** to v1 on this set (`cimeval compare` returns "within noise" on every metric). So on this evidence the shorter prompt is as good. The case for v2 has to come from a harder set, or it should be dropped.
4. **All of Opus's false alarms are on one decoy, and the label may be wrong.** Meridian's $4.6M capex is labelled as resolved, because the CIM explains it is growth capex. Opus argued, in all four runs, that capex at 55% of EBITDA still hurts cash conversion whatever it is called. That is a defensible diligence point, so the label is under review rather than counted as a clear model error.

`results/baseline/` holds the Opus 5.5 · v2 run that CI compares against.

### The hard set

The first run showed recall was saturated, so there is a second dataset, `evals/dataset_hard/`: 6 CIMs, 16 planted flags and 13 decoys. Run it with `--dataset hard`. Each flag is tagged by what it takes to find it, and recall is reported per tag:

| Tag | Example |
|---|---|
| `arithmetic` | Receivables rose 73% while revenue rose 31%. The document gives both balances but never says DSO went from 56 to 74 days. |
| `footnote` | The largest customer has given notice it will dual-source next year. It sits in a footnote under the customer table. |
| `cross_reference` | Revenue and EBITDA are pro forma for an acquisition that has not closed. The headline figure is in one paragraph and the closing condition in the next. |

Some facts on this set have more than one defensible answer, such as pro forma versus standalone revenue. Their labels list every accepted figure instead of picking one. The share of the largest customer sometimes has to be computed from a dollar amount.

## Quickstart

```bash
uv sync --extra dev
make test        # offline: dataset integrity, grader tests, agent outcome handling
make check       # offline: oracle and null baselines through the full harness
ant auth login   # or export ANTHROPIC_API_KEY
make calibrate   # judge vs. hand labels
make eval        # 8 cases × 2 reps, prompt v2
```

Compare two prompt versions:

```bash
uv run cimeval run --prompt v1 --reps 2
uv run cimeval run --prompt v2 --reps 2
uv run cimeval compare runs/<v1-run>/summary.json runs/<v2-run>/summary.json
```

Each run writes `config.json` (model, effort, prompt hash, dataset hash, git SHA), `results.jsonl`, `errors.jsonl`, a full transcript per case including every judge verdict, `summary.json` and `report.md`.

## Layout

```
src/cimscreen/        the agent: schema, prompts (v1 naive, v2 tuned), one API call
src/cimeval/          the harness: graders, judge, stats, runner, compare, report
evals/dataset/        8 synthetic CIMs and their gold labels (core set)
evals/dataset_hard/   6 harder CIMs: arithmetic, footnotes, cross-references
evals/judge_calibration.jsonl   hand-labelled judge verdicts
tests/                offline tests, no API key
.github/workflows/    ci.yml on every push; evals.yml on demand or with the run-evals PR label
```

## Limits

- **Eight cases is a demonstration, not a benchmark.** It is enough to catch a broken prompt, but not to separate two good ones by a few points. The next step is more cases, generated from a template and reviewed by hand.
- **The documents are short.** Real CIMs run 40 to 80 pages with tables. Long-context retrieval of a single qualifying sentence is a harder test than this one.
- **The labels and calibration verdicts were written by one person.** A second labeller and an agreement score would make them stronger.

## License

MIT
