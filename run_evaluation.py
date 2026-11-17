"""Evaluate reviewed development cases, with separate rule/model methods."""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from evaluation import ReviewPending, load_reviewed_cases, score_predictions
from review_cases import DEFAULT_LOCAL, DEFAULT_POLICY, DEFAULT_QUEUE, load_review_state, review_status, write_json
from routing import CALL_COST, STRATEGIES, route_with_strategy
from rule_baseline import route_by_rules
from run_example import MODEL_ID, ROOT, load_local_model
from task_policy import fingerprint, policy_hash

METHODS = ("rules", *STRATEGIES)


def evaluate_methods(predict, policy, cases, methods, on_record=None):
    if not methods or len(set(methods)) != len(methods) or set(methods) - set(METHODS):
        raise ValueError("Methods must be nonempty, known and unique")
    if predict is None and any(method != "rules" for method in methods):
        raise ValueError("Model methods require a predictor")
    records = []
    for case in cases:
        for method in methods:
            tick = time.perf_counter()
            row = {"id": case["id"], "method": method}
            try:
                detail = route_by_rules(case["state"]) if method == "rules" else route_with_strategy(
                    predict, policy, case["state"], method)
                row.update(status=detail.get("status", "ok"), detail=detail,
                           choice=detail.get("choice"), model_calls=detail["model_calls"])
                if row["status"] != "ok":
                    row["choice"] = None
                    row["error"] = detail["error"]
            except Exception as error:
                row.update(status="error", choice=None, model_calls=0,
                           error_type=type(error).__name__, error=str(error))
            row["elapsed_seconds"] = time.perf_counter() - tick
            records.append(row)
            if on_record is not None:
                on_record(row)
    scores = {method: score_predictions(cases, [row for row in records if row["method"] == method])
              for method in methods}
    return records, scores


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--local-dir", type=Path, default=DEFAULT_LOCAL)
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=["rules", "single", "sorted", "cyclic4"])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    if len(set(args.methods)) != len(args.methods):
        parser.error("Methods must not be repeated")
    policy, queue, annotations = load_review_state(args.queue, args.policy, args.local_dir)
    status = review_status(queue, annotations)
    status["policy_id"] = policy["policy_id"]
    status["planned_model_calls_if_ready"] = len(queue["items"]) * sum(CALL_COST.get(method, 0) for method in args.methods)
    if args.validate_only:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0 if status["scoring_ready"] else 2
    try:
        policy, queue, annotations, cases = load_reviewed_cases(args.queue, args.policy, args.local_dir)
    except ReviewPending as error:
        print(str(error))
        print("先运行 review_cases.py；已完成的审核会在下次继续使用。")
        return 2
    out = args.output_dir or ROOT / "outputs" / datetime.now(timezone.utc).strftime("evaluation-%Y%m%dT%H%M%S%fZ")
    if out.exists():
        parser.error("Output directory already exists")
    out.mkdir(parents=True)
    model = None
    lock = None
    load_seconds = 0
    if any(method != "rules" for method in args.methods):
        model, lock, _, load_seconds = load_local_model("cpu")
    metadata = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": queue["purpose"], "policy_id": policy["policy_id"], "policy_sha256": policy_hash(policy),
        "queue_sha256": annotations["queue_sha256"], "annotations_sha256": fingerprint(annotations),
        "model_id": MODEL_ID if model is not None else None,
        "model_revision": lock["revision"] if lock else None, "model_load_seconds": load_seconds,
        "methods": args.methods, "sample_count": len(cases),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scorer_sha256": hashlib.sha256((ROOT / "evaluation.py").read_bytes()).hexdigest(),
        "rules_sha256": hashlib.sha256((ROOT / "rule_baseline.py").read_bytes()).hexdigest(),
        "note": "Reviewed development cases previously used in model exploration; not an independent test result."}
    write_json(out / "metadata.json", metadata)
    write_json(out / "annotations.json", annotations)
    write_json(out / "reviewed_cases.json", {"cases": cases})
    with (out / "predictions.jsonl").open("w", encoding="utf-8") as stream:
        def save_record(row):
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
        records, scores = evaluate_methods(model.system_one if model is not None else None,
                                           policy, cases, args.methods, save_record)
    write_json(out / "scores.json", scores)
    print(json.dumps({method: {key: result[key] for key in (
        "sample_count", "accuracy", "macro_f1", "technical_failure_rate")}
        for method, result in scores.items()}, indent=2))
    print(f"Saved development evaluation: {out}")
    return 1 if any(row["status"] != "ok" for row in records) else 0


if __name__ == "__main__":
    sys.exit(main())
