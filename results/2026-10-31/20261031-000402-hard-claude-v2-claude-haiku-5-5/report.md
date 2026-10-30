### prompt `v2` · `claude-haiku-5-5` · effort `low`

6 cases × 2 reps · judge `claude-sonnet-5-5` · dataset `hard` `8bc54eca6fd9`

| Metric | Mean | 95% CI (cases) |
|---|---|---|
| Red-flag recall | 97% | 92% – 100% |
|   · flags that need arithmetic | 88% | 62% – 100% |
|   · flags in a footnote | 100% | 100% – 100% |
|   · flags that need two sections joined | 100% | 100% – 100% |
| Follow-up question coverage | 97% | 92% – 100% |
| Decoy false-alarm rate (lower is better) | 21% | 8% – 33% |
| Evidence quotes found verbatim | 100% | 100% – 100% |
| Financial fact accuracy | 100% | 100% – 100% |
| Recommendation in acceptable set | 100% | 100% – 100% |

| Ops | Value |
|---|---|
| Status | ok: 12 |
| Harness errors (not scored) | 0 |
| Agent cost / screen | $0.0012 |
| Judge cost / screen | $0.0236 |
| Latency p50 / max | 8.9s / 11.0s |
