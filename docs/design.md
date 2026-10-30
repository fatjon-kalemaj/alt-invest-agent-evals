# Design notes

Each decision below exists because of a specific way evals go wrong. I wrote down the failure first and then the choice that addresses it.

## The task

**Single call, not an agent loop.** The whole CIM fits in context and nothing needs to be fetched, so tools would add cost and failure modes without adding capability. If the screen later needs comparables or SEC lookups, that is when it becomes an agent.

**Structured output, validated twice.** The API constrains the response to the JSON schema generated from the Pydantic model. The harness still validates it, because a response cut off at `max_tokens` can be valid-looking but incomplete. That case is recorded as `truncated`, not as a wrong answer.

**No silent model fallback.** Production code calling Claude Opus 5.5 would normally enable server-side refusal fallbacks. An eval must not, because a fallback means the score belongs to a different model. Refusals are recorded as their own status, with their category.

## The data

**Synthetic, not real.** Real CIMs are confidential, and real public companies are in the model's training data, so it could answer from memory instead of reading. Fictional companies force it to read.

**Planted issues hide in qualifying sentences.** Each issue appears the way real ones do: the headline says growth was 22%, and two sentences later the document mentions that same-store revenue fell. A test that the issue is findable at all is built in: `tests/test_dataset.py` asserts every evidence quote is verbatim in its document.

**Decoys and a clean deal.** Without them, "flag everything" is the optimal policy. The decoys are things a nervous reader would flag but the document already resolves.

**Recommendations are labelled as sets.** Two careful associates could disagree between "needs more info" and "pass" on most of these deals. Scoring one of them as wrong would measure the labeller's taste.

## The graders

**Code where possible, judge where necessary.** Numbers, quotes and the recommendation are checked in code: deterministic, free, and run in CI. Only "did it identify this issue" needs a judge, because the same issue can be phrased many ways.

**One question per judge call.** A judge asked "rate this screen 1–10" is hard to calibrate and tells you nothing about what was missed. Each call here answers one yes/no question about one issue.

**The judge sees the issue, not a model answer.** The gold label is a description of the issue written by a person, not another model's output. So the judge rewards finding the issue, not imitating a reference model's wording.

**Judge rubric targets specificity.** "Customer concentration" does not count if the issue is that the top customer's contract expires in four months. The calibration set includes this exact trap.

**Candidate output is treated as data.** The judge prompt says so, and calibration item `c10` hides an instruction to the grader inside the agent's output to check that it is ignored.

**Evidence grounding is a hard floor.** A screen that quotes the document wrongly is worse than one that misses an issue, because it teaches the reader to stop checking. CI fails if grounding drops below 95% regardless of anything else.

## The harness

| Failure | Guard |
|---|---|
| An API error scored as a model failure | Exceptions go to `errors.jsonl`, never into results |
| A truncated answer scored as wrong | `status: truncated`, excluded from quality means, shown in ops |
| The wrong model answered | `response.model` asserted on every agent and judge call |
| A broken grader producing plausible numbers | Oracle must score 100%, null must score near zero; both run in CI |
| Reps treated as independent samples | Averaged within case, then bootstrapped across cases |
| A small difference read as an improvement | `compare` reports paired differences with 95% intervals and says "within noise" when it is |
| Retries hiding inside latency | Retries are done in our code and counted per row; latency is the final request only |
| Judge cost hiding inside agent cost | Recorded separately per row |
| Not knowing why a score changed | Full transcript per case: raw output, usage, request ID, every judge verdict with its reasoning |

## Noise floor

With 8 cases, a pass-rate metric has a 95% interval of roughly ±35 points at one rep and ±25 at two. That is enough to catch a broken prompt, and not enough to choose between two good ones. The levers, cheapest first: more reps, more cases, then trimming to the cases where variants actually disagree.
