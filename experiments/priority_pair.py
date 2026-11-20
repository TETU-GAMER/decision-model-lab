"""Run paired ticket-routing comparisons on holdout-024."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from experiments.prompt_ablation import CLARIFY
from experiments.two_stage_routing import HOLDOUT_QUEUE, checked_holdout_protocol, route_two_stage, stage_prompts
from review_cases import DEFAULT_POLICY, write_json
from routing import run_choice_call
from run_example import ROOT, load_local_model
from task_policy import fingerprint, load_policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    comparison = parser.add_mutually_exclusive_group()
    comparison.add_argument("--compare-position", action="store_true",
                            help="Compare the same priority sentence at the end and at the beginning")
    comparison.add_argument("--compare-credit-only", action="store_true",
                            help="Compare the priority-first ticket with and without the delivery request")
    args = parser.parse_args()
    queue = json.loads(HOLDOUT_QUEUE.read_text(encoding="utf-8-sig"))
    policy = load_policy(DEFAULT_POLICY)
    prompts = stage_prompts(policy, "route-first")
    protocol = checked_holdout_protocol(queue, policy, prompts)
    source_id = "holdout-024"
    original = next(case["state"] for case in queue["items"] if case["id"] == source_id)
    addition = "Please check the missing credit first."
    appended = original + " " + addition
    priority_first = ("priority_first", addition + " " + original, "billing")
    if args.compare_credit_only:
        credit_only = addition + " Last month's credit is missing from my balance. I'd like this sorted out today."
        cases = [priority_first, ("credit_only", credit_only, "billing")]
    elif args.compare_position:
        cases = [("priority_last", appended, "billing"), priority_first]
    else:
        cases = [("both_today", original, CLARIFY), ("credit_first", appended, "billing")]

    started = datetime.now(timezone.utc)
    out = args.output_dir or ROOT / "outputs" / started.strftime("priority-pair-%Y%m%dT%H%M%S%fZ")
    out.mkdir(parents=True, exist_ok=False)
    model, lock, _, _ = load_local_model("cpu")
    cutoff = protocol["clarification_threshold"]
    rows = []
    for name, text, expected in cases:
        result = route_two_stage(model.system_one, prompts, text, clarification_threshold=cutoff)
        rows.append({"variant": name, "state": text, "expected": expected, **result})
        print(f"{name}: expected {expected}, observed {result['choice']} ({result['status']})")
    report = {
        "created_at_utc": started.isoformat(), "source_id": source_id, "added_sentence": addition,
        "model_id": lock["model_id"], "model_revision": lock["revision"],
        "device": str(next(model.parameters()).device), "protocol_sha256": fingerprint(protocol),
        "gate_order": protocol["gate_order"], "clarification_threshold": cutoff,
        "threshold_comparison": protocol["threshold_comparison"], "cases": rows,
    }
    if args.compare_credit_only:
        single = next(row for row in rows if row["variant"] == "credit_only")
        if single["choice"] == CLARIFY:
            department = prompts["department"]
            call, route = run_choice_call(model.system_one, department, single["state"], list(department["criteria"]))
            report["department_only_check"] = {"variant": single["variant"], "call": call}
            print(f"Credit-only department check: {route['choice'] if route else 'error'}")
    write_json(out / "pair.json", report)
    if "department_only_check" in report and report["department_only_check"]["call"]["status"] != "ok":
        return 1
    return int(any(row["status"] != "ok" for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
