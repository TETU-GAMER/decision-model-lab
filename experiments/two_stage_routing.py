"""Evaluate a clarification decision followed by conditional department selection."""

import argparse
import hashlib
import json
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from evaluation import ReviewPending, load_reviewed_cases
from experiments.prompt_ablation import CLARIFY, CLARIFY_DESCRIPTION, summarize
from review_cases import DEFAULT_LOCAL, DEFAULT_POLICY, DEFAULT_QUEUE, HOLDOUT_PURPOSE, write_json
from routing import run_choice_call
from run_evaluation import annotation_provenance
from run_example import ROOT, load_local_model
from task_policy import fingerprint, policy_hash


GATE_ORDERS = {
    "route-first": ("route_to_team", CLARIFY),
    "clarification-first": (CLARIFY, "route_to_team"),
}
HOLDOUT_CUTOFF = 0.26
HOLDOUT_QUEUE = ROOT / "data" / "holdout_review_v1.json"
HOLDOUT_LOCAL = DEFAULT_LOCAL / "holdout_v1"
HOLDOUT_PROTOCOL = ROOT / "data" / "holdout_protocol_v1.json"


def stage_prompts(policy, gate_order="route-first"):
    gate_descriptions = {
        "route_to_team": "One team can handle the customer's main issue or stated priority.",
        CLARIFY: CLARIFY_DESCRIPTION,
    }
    return {
        "gate": {
            "instructions": (
                "Can you assign this ticket to one of billing, technical support, or delivery? "
                "Route it if the main issue identifies one team, including when the customer "
                "says which issue to handle first. Ask for clarification if the message is too "
                "vague to identify a team or gives equal priority to independent issues for "
                "different teams."
            ),
            "criteria": {key: gate_descriptions[key] for key in GATE_ORDERS[gate_order]},
        },
        "department": {
            "instructions": (
                "Choose the team that best matches the customer's main issue. "
                "If the customer says which issue to handle first, use that issue."
            ),
            "criteria": {key: value for key, value in policy["criteria"].items() if key != CLARIFY},
        },
    }


def checked_holdout_protocol(queue, policy, prompts):
    protocol = json.loads(HOLDOUT_PROTOCOL.read_text(encoding="utf-8-sig"))
    lock = json.loads((ROOT / "model-lock.json").read_text(encoding="utf-8-sig"))
    expected = {
        "queue_sha256": fingerprint(queue), "policy_sha256": policy_hash(policy),
        "gate_order": "route-first", "clarification_threshold": HOLDOUT_CUTOFF, "threshold_comparison": ">=",
        "model_id": lock["model_id"], "model_revision": lock["revision"],
        "prompts_sha256": fingerprint(prompts),
        "candidate_order": {stage: list(config["criteria"]) for stage, config in prompts.items()},
    }
    if queue["purpose"] != HOLDOUT_PURPOSE:
        raise ValueError("Expected a prospective review queue")
    for key, value in expected.items():
        if protocol.get(key) != value:
            raise ValueError(f"Frozen holdout protocol mismatch for {key}")
    return protocol


def route_two_stage(predict, prompts, state, *, clarification_threshold=None):
    if not isinstance(state, str) or not state.strip():
        raise ValueError("Ticket text must not be empty")
    calls = []
    for stage in ("gate", "department"):
        config = prompts[stage]
        call, route = run_choice_call(predict, config, state, list(config["criteria"]))
        calls.append({"stage": stage, **call})
        if route is None:
            return {"status": "error", "choice": None, "model_calls": len(calls), "raw_calls": calls}
        choice = route["choice"]
        if stage == "gate" and clarification_threshold is not None:
            score = route["probabilities"][CLARIFY]
            choice = CLARIFY if score >= clarification_threshold else "route_to_team"
            calls[-1]["threshold_decision"] = choice
        if choice == CLARIFY:
            break
    return {"status": "ok", "choice": choice, "model_calls": len(calls), "raw_calls": calls}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--gate-order", choices=GATE_ORDERS, default="route-first")
    parser.add_argument("--holdout", action="store_true",
                        help="Evaluate the frozen 26%% prospective batch after its review is complete")
    args = parser.parse_args(argv)
    if args.holdout and args.gate_order != "route-first":
        parser.error("--holdout requires route-first")
    queue_path, local_dir = (HOLDOUT_QUEUE, HOLDOUT_LOCAL) if args.holdout else (DEFAULT_QUEUE, DEFAULT_LOCAL)
    try:
        policy, queue, annotations, cases = load_reviewed_cases(queue_path, DEFAULT_POLICY, local_dir)
    except ReviewPending as error:
        print(error)
        return 2
    prompts = stage_prompts(policy, args.gate_order)
    protocol = checked_holdout_protocol(queue, policy, prompts) if args.holdout else None
    cutoff = protocol["clarification_threshold"] if protocol is not None else None
    started = datetime.now(timezone.utc)
    out = args.output_dir or ROOT / "outputs" / started.strftime("two-stage-%Y%m%dT%H%M%S%fZ")
    out.mkdir(parents=True, exist_ok=False)

    model, lock, _, load_seconds = load_local_model("cpu")
    import torch

    parameter = next(model.parameters())
    metadata = {
        "created_at_utc": started.isoformat(),
        "purpose": queue["purpose"],
        "sample_count": len(cases),
        "queue_sha256": annotations["queue_sha256"],
        "annotations_sha256": fingerprint(annotations),
        "annotation_provenance": annotation_provenance(annotations),
        "policy_id": policy["policy_id"],
        "policy_sha256": policy_hash(policy),
        "model_id": lock["model_id"],
        "model_revision": lock["revision"],
        "model_load_seconds": load_seconds,
        "strategy": "two_stage",
        "gate_order": args.gate_order,
        "candidate_order": {stage: list(config["criteria"]) for stage, config in prompts.items()},
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "device": str(parameter.device),
            "dtype": str(parameter.dtype),
            "torch_threads": torch.get_num_threads(),
            "packages": {name: version(name) for name in (
                "torch", "transformers", "safetensors", "huggingface_hub", "tokenizers",
            )},
        },
    }
    if protocol is not None:
        metadata["annotation_provenance"]["note"] = (
            "Review labels were recorded before model predictions on the synthetic holdout. "
            "Assistance counts describe how the labels were supplied."
        )
        metadata.update(clarification_threshold=cutoff, threshold_comparison=">=",
                        protocol_sha256=fingerprint(protocol))
    write_json(out / "metadata.json", metadata)
    write_json(out / "prompts.json", prompts)
    records = []
    stage_calls = Counter()
    with (out / "predictions.jsonl").open("w", encoding="utf-8") as stream:
        for case in cases:
            result = route_two_stage(model.system_one, prompts, case["state"], clarification_threshold=cutoff)
            stage_calls.update(call["stage"] for call in result["raw_calls"])
            row = {"id": case["id"], "variant": "two_stage", **result}
            records.append(row)
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
    score = summarize(cases, records)
    score["stage_model_calls"] = {stage: stage_calls[stage] for stage in prompts}
    score["total_model_calls"] = sum(stage_calls.values())
    if protocol is not None:
        score["assignable_support"] = len(cases) - score["clarification_support"]
        score["correct_department_assignments"] = score["correct"] - score["correct_clarifications"]
    write_json(out / "scores.json", {"two_stage": score})
    print(f"{score['correct']}/{len(cases)} correct, {score['incorrect_clarifications']} "
          f"incorrect clarifications, {score['correct_clarifications']}/{score['clarification_support']} "
          f"required clarifications kept, {score['total_model_calls']} model calls, "
          f"{score['technical_failures']} technical failures")
    print(f"Saved two-stage evaluation: {out}")
    return int(score["technical_failures"] > 0)


if __name__ == "__main__":
    sys.exit(main())
