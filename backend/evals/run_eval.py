from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.db import SessionLocal
from app.eval_runner import (
    DEFAULT_STRATEGIES,
    aggregate_results,
    aggregate_results_by_workload,
    build_decision_highlights,
    build_shadow_comparisons,
    compute_baseline_deltas,
    compute_workload_winners,
    load_dataset,
    render_markdown_report,
    run_policy_dry_runs,
    run_single_example,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline routing evaluation against the local router backend.")
    parser.add_argument(
        "--dataset",
        default=str(BASE_DIR / "evals" / "datasets" / "sample_workloads.json"),
        help="Path to the dataset JSON file.",
    )
    parser.add_argument(
        "--output-json",
        default=str(BASE_DIR / "evals" / "results" / "latest_report.json"),
        help="Path to the output JSON report.",
    )
    parser.add_argument(
        "--output-md",
        default=str(BASE_DIR / "evals" / "results" / "latest_report.md"),
        help="Path to the output Markdown summary.",
    )
    parser.add_argument(
        "--strategies",
        nargs="*",
        default=DEFAULT_STRATEGIES,
        help="Strategies to evaluate.",
    )
    parser.add_argument(
        "--baseline",
        default="current_production_policy",
        help="Baseline strategy for delta comparison.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    dataset = load_dataset(args.dataset)
    examples = dataset.get("examples", [])
    results = []

    db = SessionLocal()
    try:
        for example in examples:
            for strategy in args.strategies:
                results.append(run_single_example(db=db, example=example, strategy=strategy))
    finally:
        db.close()

    summary = aggregate_results(results)
    summary = compute_baseline_deltas(summary, baseline_strategy=args.baseline)
    workload_summary = aggregate_results_by_workload(results)
    workload_winners = compute_workload_winners(workload_summary)
    decision_highlights = build_decision_highlights(results)
    shadow_comparisons = build_shadow_comparisons(results, baseline_strategy=args.baseline)
    policy_db = SessionLocal()
    try:
        policy_dry_runs = [
            item.to_dict()
            for item in run_policy_dry_runs(
                db=policy_db,
                dataset=dataset,
                strategies=args.strategies,
            )
        ]
    finally:
        policy_db.close()
    report = {
        "dataset_name": dataset.get("dataset_name", "unnamed"),
        "strategies": args.strategies,
        "baseline_strategy": args.baseline,
        "summary": summary,
        "workload_summary": workload_summary,
        "workload_winners": workload_winners,
        "decision_highlights": decision_highlights,
        "shadow_comparisons": shadow_comparisons,
        "policy_dry_runs": policy_dry_runs,
        "results": [item.to_dict() for item in results],
    }

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md.write_text(
        render_markdown_report(
            dataset_name=report["dataset_name"],
            strategies=args.strategies,
            summary=summary,
            workload_summary=workload_summary,
            workload_winners=workload_winners,
            decision_highlights=decision_highlights,
            shadow_comparisons=shadow_comparisons,
            policy_dry_runs=policy_dry_runs,
        ),
        encoding="utf-8",
    )

    print(f"Wrote JSON report to {output_json}")
    print(f"Wrote Markdown report to {output_md}")


if __name__ == "__main__":
    main()
