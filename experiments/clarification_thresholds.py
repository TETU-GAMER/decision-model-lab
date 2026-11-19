"""Replay the first-stage clarification scores against a reviewed development set."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from evaluation import load_reviewed_cases
from experiments.order_sensitivity import build_request, validate_response
from experiments.prompt_ablation import CLARIFY, summarize
from experiments.two_stage_routing import GATE_ORDERS, stage_prompts
from review_cases import DEFAULT_LOCAL, DEFAULT_POLICY, DEFAULT_QUEUE, write_json
from run_example import ROOT
from task_policy import fingerprint, policy_hash


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_arm(directory, order, policy, cases, binding):
    prompts = stage_prompts(policy, order)
    orders = {stage: list(prompt["criteria"]) for stage, prompt in prompts.items()}
    metadata = read_json(directory / "metadata.json")
    expected_metadata = {**binding, "gate_order": order, "candidate_order": orders}
    for key, expected in expected_metadata.items():
        if metadata.get(key) != expected:
            raise ValueError(f"{order}: metadata mismatch for {key}")
    saved_prompts = read_json(directory / "prompts.json")
    if saved_prompts != prompts or any(list(saved_prompts[s]["criteria"]) != ids for s, ids in orders.items()):
        raise ValueError(f"{order}: prompts differ from the two-stage setup")

    with (directory / "predictions.jsonl").open(encoding="utf-8-sig") as stream:
        rows = [json.loads(line) for line in stream]
    scores = summarize(cases, rows)
    saved_scores = read_json(directory / "scores.json")["two_stage"]
    if any(saved_scores.get(key) != value for key, value in scores.items()) or scores["technical_failures"]:
        raise ValueError(f"{order}: incomplete predictions or inconsistent archived scores")

    by_id = {row["id"]: row for row in rows}
    tickets = []
    for case in cases:
        row = by_id[case["id"]]
        calls = row["raw_calls"]
        if row["variant"] != "two_stage" or row["model_calls"] != 2 or len(calls) != 2:
            raise ValueError(f"{case['id']}: replay needs both original model calls")
        routes = {}
        for stage, call in zip(("gate", "department"), calls, strict=True):
            request = build_request(prompts[stage], case, orders[stage])
            if (call["stage"] != stage or call["status"] != "ok" or call["request"] != request
                    or call["candidate_order"] != orders[stage]
                    or list(call["request"]["questions"]["route"]["criteria"]) != orders[stage]):
                raise ValueError(f"{case['id']}: unexpected {stage} call")
            routes[stage] = validate_response(call["response"], orders[stage])
        if routes["gate"]["choice"] != "route_to_team" or routes["department"]["choice"] != row["choice"]:
            raise ValueError(f"{case['id']}: saved choices disagree")
        tickets.append({"id": case["id"], "gold": case["gold"], "department": row["choice"],
                        "p_clarification": routes["gate"]["probabilities"][CLARIFY]})
    return tickets


def describe(scores):
    return {"count": len(scores), "min": min(scores, default=None),
            "median": median(scores) if scores else None, "max": max(scores, default=None)}


def analyze_thresholds(tickets):
    """Apply inclusive cutoffs to full-precision scores, keeping department choices fixed."""
    positives = [t["p_clarification"] for t in tickets if t["gold"] == CLARIFY]
    assignable = [t["p_clarification"] for t in tickets if t["gold"] != CLARIFY]
    protected = [t["p_clarification"] for t in tickets if t["department"] == t["gold"]]
    groups = {"needs_clarification": describe(positives), "assignable": describe(assignable),
              "correctly_routed": describe(protected)}

    thresholds = []
    for cutoff in [None, *sorted(set(positives + assignable), reverse=True)]:
        # None represents every threshold above the largest observed score.
        recovered = sum(score >= cutoff for score in positives) if cutoff is not None else 0
        false_clarifications = sum(score >= cutoff for score in assignable) if cutoff is not None else 0
        retained = sum(score < cutoff for score in protected) if cutoff is not None else len(protected)
        thresholds.append({"threshold": cutoff, "recovered_clarifications": recovered,
                           "missed_clarifications": len(positives) - recovered,
                           "retained_correct_routes": retained, "false_clarifications": false_clarifications,
                           "wrong_department": len(assignable) - false_clarifications - retained,
                           "correct": recovered + retained})

    # Descending traversal makes the less intrusive cutoff win a tie.
    recover_all = max((row for row in thresholds if row["recovered_clarifications"] == len(positives)),
                      key=lambda row: row["retained_correct_routes"])
    preserve_all = max((row for row in thresholds if row["retained_correct_routes"] == len(protected)),
                       key=lambda row: row["recovered_clarifications"])
    return {"groups": groups, "thresholds": thresholds,
            "goals": {"recover_all": recover_all, "preserve_all": preserve_all,
                      "both_possible": recover_all["retained_correct_routes"] == len(protected)},
            "gate_scores": [{"id": t["id"], "p_clarification": t["p_clarification"]} for t in tickets]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=ROOT / "results" / "two-stage-v1",
                        help="Directory containing both archived gate orders")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    policy, queue, annotations, cases = load_reviewed_cases(DEFAULT_QUEUE, DEFAULT_POLICY, DEFAULT_LOCAL)
    lock = read_json(ROOT / "model-lock.json")
    binding = {"strategy": "two_stage", "purpose": queue["purpose"], "sample_count": len(cases),
               "model_id": lock["model_id"], "model_revision": lock["revision"],
               "annotations_sha256": fingerprint(annotations), "queue_sha256": fingerprint(queue),
               "policy_id": policy["policy_id"], "policy_sha256": policy_hash(policy)}
    analyses = {}
    previous_departments = None
    for order in GATE_ORDERS:
        tickets = read_arm(args.run_dir / order, order, policy, cases, binding)
        departments = {t["id"]: t["department"] for t in tickets}
        if previous_departments is not None and previous_departments != departments:
            raise ValueError("Gate orders differ in their archived department decisions")
        previous_departments = departments
        analyses[order] = analyze_thresholds(tickets)

    out = args.output_dir or ROOT / "outputs" / datetime.now(timezone.utc).strftime("thresholds-%Y%m%dT%H%M%S%fZ")
    out.mkdir(parents=True, exist_ok=False)
    summary = {"source": binding, "score": "gate.probabilities.needs_clarification",
               "threshold_rule": "Clarify when the score is at least the cutoff. A null cutoff routes all tickets.",
               "orders": {}}
    for order, analysis in analyses.items():
        write_json(out / f"{order}.json", analysis)
        summary["orders"][order] = {
            "distinct_threshold_outcomes": len(analysis["thresholds"]),
            "groups": analysis["groups"],
            "goals": analysis["goals"],
        }
    write_json(out / "summary.json", summary)
    print(f"Saved offline threshold replay for {len(cases)} reviewed tickets in {out}")


if __name__ == "__main__":
    main()
