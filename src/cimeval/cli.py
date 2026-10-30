"""cimeval: run, compare and calibrate.

  cimeval run --agent claude --prompt v2 --reps 2
  cimeval run --agent oracle --no-judge        # offline harness check
  cimeval compare results/baseline/summary.json runs/<id>/summary.json
  cimeval calibrate-judge
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

from cimscreen.agent import DEFAULT_MODEL, PROMPTS_DIR, ScreenResult, screen
from cimscreen.pricing import cost_usd
from cimscreen.schema import Screen

from . import report
from .baselines import null_screen, oracle_screen
from .dataset import DATASET_DIR, DATASETS, Case, dataset_hash, load_cases
from .graders import grade_code
from .judge import DEFAULT_JUDGE_MODEL, grade_judged, judge_decoy, judge_flag
from .stats import LOWER_IS_BETTER, METRICS, paired_diff, summarize

ROOT = Path(__file__).resolve().parents[2]


def _git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def _baseline_result(s: Screen) -> ScreenResult:
    return ScreenResult(status="ok", screen=s, raw_text=s.model_dump_json(), stop_reason=None,
                        served_model="baseline", usage={}, latency_s=0.0, attempts=0)


def run_one(args, client, case: Case, rep: int) -> tuple[dict | None, dict | None, dict]:
    """Returns (result row, error row, transcript). Exactly one of row/error is set."""
    transcript = {"case_id": case.case_id, "rep": rep}
    try:
        if args.agent == "oracle":
            result = _baseline_result(oracle_screen(case))
        elif args.agent == "null":
            result = _baseline_result(null_screen(case))
        else:
            result = screen(case.document, prompt_version=args.prompt, model=args.model, effort=args.effort, client=client)

        transcript["agent"] = {"status": result.status, "stop_reason": result.stop_reason, "raw_text": result.raw_text,
                               "usage": result.usage, "request_id": result.request_id, "error": result.error}
        row = {
            "case_id": case.case_id, "rep": rep, "status": result.status, "stop_reason": result.stop_reason,
            "served_model": result.served_model, "attempts": result.attempts, "latency_s": result.latency_s,
            "usage": result.usage, "agent_cost_usd": cost_usd(args.model, result.usage) if args.agent == "claude" else None,
            "refusal_category": result.refusal_category, "metrics": None,
        }
        if result.status != "ok":
            # Truncations and refusals are recorded and counted, never averaged in as wrong answers.
            return row, None, transcript

        metrics = grade_code(case, result.screen)
        if not args.no_judge:
            judged, verdicts, judge_usage = grade_judged(client, args.judge_model, case.labels, result.screen)
            metrics.update(judged)
            transcript["judge"] = verdicts
            row["judge_usage"] = judge_usage
            row["judge_cost_usd"] = cost_usd(args.judge_model, judge_usage)
        row["metrics"] = metrics
        return row, None, transcript
    except Exception as e:  # plumbing, not a model outcome: goes to errors.jsonl
        transcript["exception"] = traceback.format_exc()
        return None, {"case_id": case.case_id, "rep": rep, "error_class": type(e).__name__, "error": str(e)[:1000]}, transcript


def cmd_run(args) -> int:
    dataset_dir = DATASETS[args.dataset]
    cases = load_cases(dataset_dir, only=args.cases.split(",") if args.cases else None)
    needs_api = args.agent == "claude" or not args.no_judge
    client = anthropic.Anthropic(max_retries=0, timeout=300.0) if needs_api else None

    prompt_text = (PROMPTS_DIR / f"{args.prompt}.md").read_text()
    run_id = time.strftime("%Y%m%d-%H%M%S") + f"-{args.dataset}-{args.agent}-{args.prompt}"
    out = Path(args.out) / run_id
    (out / "transcripts").mkdir(parents=True)
    config = {
        "run_id": run_id, "agent": args.agent, "prompt_version": args.prompt,
        "prompt_sha": hashlib.sha256(prompt_text.encode()).hexdigest()[:12],
        "model": args.model if args.agent == "claude" else args.agent, "effort": args.effort, "reps": args.reps,
        "judge_model": None if args.no_judge else args.judge_model, "dataset": args.dataset, "dataset_hash": dataset_hash(dataset_dir), "git_sha": _git_sha(),
    }
    (out / "config.json").write_text(json.dumps(config, indent=2))

    jobs = [(c, r) for c in cases for r in range(args.reps)]
    print(f"Running {len(jobs)} screens ({len(cases)} cases × {args.reps} reps) → {out}", file=sys.stderr)
    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for row, err, transcript in pool.map(lambda j: run_one(args, client, *j), jobs):
            (out / "transcripts" / f"{transcript['case_id']}__r{transcript['rep']}.json").write_text(json.dumps(transcript, indent=2, default=str))
            if row:
                rows.append(row)
                print(f"  {row['case_id']} r{row['rep']}: {row['status']}", file=sys.stderr)
            else:
                errors.append(err)
                print(f"  {err['case_id']} r{err['rep']}: HARNESS ERROR {err['error_class']}", file=sys.stderr)

    rows.sort(key=lambda r: (r["case_id"], r["rep"]))
    (out / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (out / "errors.jsonl").write_text("".join(json.dumps(e) + "\n" for e in errors))
    summary = {"quality": summarize(rows), "ops": report.ops_summary(rows, errors)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    md = report.render(config, summary)
    (out / "report.md").write_text(md)
    print(md)
    return 1 if errors else 0


GATED = ("flag_recall", "decoy_false_alarm", "grounding", "fact_accuracy", "abstention")


def cmd_compare(args) -> int:
    base = json.loads(Path(args.base).read_text())["quality"]
    new = json.loads(Path(args.new).read_text())["quality"]
    lines = ["| Metric | Base | New | Δ (paired) | 95% CI | Verdict |", "|---|---|---|---|---|---|"]
    failed = False
    for m in METRICS:
        d = paired_diff(base, new, m)
        if d is None:
            continue
        sign = -1 if m in LOWER_IS_BETTER else 1
        better = sign * d["mean_diff"]
        lo, hi = sorted(sign * x for x in d["ci95"])
        if m in GATED and (better < -args.tolerance or hi < 0):
            verdict, failed = "❌ regression", True
        elif lo > 0:
            verdict = "✅ improved"
        else:
            verdict = "≈ within noise"
        lines.append(f"| {m} | {base[m]['mean']:.2f} | {new[m]['mean']:.2f} | {d['mean_diff']:+.2f} | "
                     f"[{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}] | {verdict} |")
    if "grounding" in new and new["grounding"]["mean"] < args.grounding_floor:
        lines.append(f"\n❌ Grounding {new['grounding']['mean']:.2f} is below the hard floor {args.grounding_floor}.")
        failed = True
    print("\n".join(lines))
    return 1 if failed else 0


def cmd_calibrate(args) -> int:
    """Agreement between the judge and hand-labelled verdicts."""
    client = anthropic.Anthropic(max_retries=0, timeout=300.0)
    labels = {c.case_id: c.labels for c in load_cases()}
    items = [json.loads(l) for l in (DATASET_DIR.parent / "judge_calibration.jsonl").read_text().splitlines() if l.strip()]
    agree, disagreements = 0, []
    for item in items:
        candidate = Screen.model_validate(item["candidate"])
        case = labels[item["case_id"]]
        if item["kind"] == "flag":
            target = next(f for f in case["planted_flags"] if f["id"] == item["target_id"])
            got = judge_flag(client, args.judge_model, target, candidate).verdict.identified
        else:
            target = next(d for d in case["decoys"] if d["id"] == item["target_id"])
            got = judge_decoy(client, args.judge_model, target, candidate).verdict.raised_as_open_risk
        if got == item["human_label"]:
            agree += 1
        else:
            disagreements.append(f"{item['id']}: human={item['human_label']} judge={got} ({item['note']})")
    rate = agree / len(items)
    print(f"Judge {args.judge_model} agrees with human labels on {agree}/{len(items)} ({rate:.0%}).")
    for d in disagreements:
        print("  disagree:", d)
    return 0 if rate >= args.min_agreement else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="cimeval")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the agent over the dataset and grade it")
    r.add_argument("--agent", choices=["claude", "oracle", "null"], default="claude")
    r.add_argument("--prompt", default="v2", help="prompt version in src/cimscreen/prompts/")
    r.add_argument("--model", default=DEFAULT_MODEL)
    r.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    r.add_argument("--reps", type=int, default=1)
    r.add_argument("--dataset", choices=sorted(DATASETS), default="core")
    r.add_argument("--cases", help="comma-separated case ids (default: all)")
    r.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    r.add_argument("--no-judge", action="store_true", help="code graders only; no API calls for grading")
    r.add_argument("--concurrency", type=int, default=4)
    r.add_argument("--out", default=str(ROOT / "runs"))
    r.set_defaults(fn=cmd_run)

    c = sub.add_parser("compare", help="paired comparison of two runs; exits 1 on regression")
    c.add_argument("base")
    c.add_argument("new")
    c.add_argument("--tolerance", type=float, default=0.10, help="max allowed mean drop on gated metrics")
    c.add_argument("--grounding-floor", type=float, default=0.95)
    c.set_defaults(fn=cmd_compare)

    k = sub.add_parser("calibrate-judge", help="judge agreement with hand labels")
    k.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    k.add_argument("--min-agreement", type=float, default=0.9)
    k.set_defaults(fn=cmd_calibrate)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
