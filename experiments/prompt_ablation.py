"""Compare original, isolated, and combined prompts on the reviewed development set."""

import argparse
import hashlib
import json
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from evaluation import load_reviewed_cases, score_predictions
from review_cases import DEFAULT_LOCAL, DEFAULT_POLICY, DEFAULT_QUEUE, write_json
from routing import route_with_strategy
from run_evaluation import annotation_provenance
from run_example import ROOT, load_local_model
from task_policy import fingerprint, policy_hash

CLARIFY = "needs_clarification"
INSTRUCTIONS = (
    "Choose the team that best matches the customer's main issue. "
    "If the customer says which issue to handle first, use that issue. "
    "Choose needs_clarification only if the request is too vague to identify a team "
    "or gives equal priority to issues for different teams."
)
CLARIFY_DESCRIPTION = (
    "Ask a follow-up question only when the message is too vague to pick a team, "
    "or when issues for different teams are equally important."
)


def variants(policy):
    revised_criteria = {**policy["criteria"], CLARIFY: CLARIFY_DESCRIPTION}
    return {
        "original": policy,
        "instruction_only": {**policy, "instructions": INSTRUCTIONS},
        "clarification_description_only": {**policy, "criteria": revised_criteria},
        "combined": {**policy, "instructions": INSTRUCTIONS, "criteria": revised_criteria},
    }


def summarize(cases, rows):
    score = score_predictions(cases, rows)
    counts = Counter(row["choice"] for row in rows if row["status"] == "ok")
    matrix = score["confusion_matrix"]
    return {**score, "prediction_counts": dict(counts),
            "predicted_clarification": counts[CLARIFY],
            "incorrect_clarifications": sum(matrix[label][CLARIFY] for label in matrix if label != CLARIFY),
            "correct_clarifications": matrix[CLARIFY][CLARIFY],
            "clarification_support": score["per_class"][CLARIFY]["support"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--variant", choices=("original", "instruction_only", "clarification_description_only", "combined"),
                        help="Run just one condition, or omit to rerun the original three conditions")
    args = parser.parse_args()
    policy, queue, annotations, cases = load_reviewed_cases(DEFAULT_QUEUE, DEFAULT_POLICY, DEFAULT_LOCAL)
    available = variants(policy)
    selected = [args.variant] if args.variant else ["original", "instruction_only", "clarification_description_only"]
    prompts = {name: available[name] for name in selected}
    out = args.output_dir or ROOT / "outputs" / datetime.now(timezone.utc).strftime("prompt-ablation-%Y%m%dT%H%M%S%fZ")
    out.mkdir(parents=True, exist_ok=False)
    model, lock, _, load_seconds = load_local_model("cpu")
    import torch

    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": queue["purpose"], "sample_count": len(cases),
        "annotation_provenance": annotation_provenance(annotations),
        "annotations_sha256": fingerprint(annotations), "queue_sha256": annotations["queue_sha256"],
        "policy_sha256": policy_hash(policy), "policy_id": policy["policy_id"],
        "model_id": lock["model_id"], "model_revision": lock["revision"],
        "strategy": "single", "candidate_order": list(policy["criteria"]), "model_load_seconds": load_seconds,
        "variants": selected, "planned_model_calls": len(cases) * len(selected),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "environment": {"python": sys.version.split()[0], "platform": platform.platform(),
                        "device": str(next(model.parameters()).device), "torch_threads": torch.get_num_threads(),
                        "dtype": str(next(model.parameters()).dtype),
                        "packages": {name: version(name) for name in ("torch", "transformers", "safetensors", "huggingface_hub", "tokenizers")}},
    }
    write_json(out / "metadata.json", metadata)
    write_json(out / "prompts.json", {name: {key: config[key] for key in ("instructions", "criteria")}
                                     for name, config in prompts.items()})
    records = {name: [] for name in prompts}
    with (out / "predictions.jsonl").open("w", encoding="utf-8") as stream:
        for case in cases:
            for name, config in prompts.items():
                detail = route_with_strategy(model.system_one, config, case["state"], "single")
                row = {"id": case["id"], "variant": name, "status": detail["status"],
                       "choice": detail.get("choice"), "detail": detail}
                records[name].append(row)
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
    scores = {name: summarize(cases, rows) for name, rows in records.items()}
    write_json(out / "scores.json", scores)
    for name, score in scores.items():
        print(f"{name}: {score['correct']}/{len(cases)} correct, "
              f"{score['predicted_clarification']} clarification predictions, "
              f"{score['incorrect_clarifications']} incorrect clarifications, "
              f"{score['technical_failures']} technical failures")
    print(f"Saved prompt comparison: {out}")
    return int(any(score["technical_failures"] for score in scores.values()))


if __name__ == "__main__":
    sys.exit(main())
