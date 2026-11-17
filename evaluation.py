"""Four-class scoring with explicit technical failures and human-review gates."""
from collections import Counter

from review_cases import load_review_state, review_status
from task_policy import LABELS


class ReviewPending(ValueError):
    pass


def load_reviewed_cases(queue_path, policy_path, local_dir):
    policy, queue, annotations = load_review_state(queue_path, policy_path, local_dir)
    status = review_status(queue, annotations)
    if not status["scoring_ready"]:
        raise ReviewPending(f"人工审核尚未完成：{status['reviewed_cases']}/{status['total_cases']}；暂不计算准确率。")
    reviews = {row["id"]: row for row in annotations["reviews"]}
    cases = [{"id": case["id"], "state": case["state"], "gold": reviews[case["id"]]["label"]}
             for case in queue["items"]]
    return policy, queue, annotations, cases


def score_predictions(cases, predictions):
    if not cases:
        raise ValueError("Cannot score an empty dataset")
    ids = [case["id"] for case in cases]
    if len(set(ids)) != len(ids) or any(case["gold"] not in LABELS for case in cases):
        raise ValueError("Gold cases need unique IDs and valid labels")
    by_id = {}
    for prediction in predictions:
        if prediction["id"] not in ids or prediction["id"] in by_id:
            raise ValueError("Unknown or duplicate prediction ID")
        if prediction["status"] == "ok":
            if prediction.get("choice") not in LABELS:
                raise ValueError("Successful prediction has no valid choice")
        elif prediction["status"] != "error" or prediction.get("choice") is not None:
            raise ValueError("Failed predictions must use status=error and choice=null")
        by_id[prediction["id"]] = prediction
    matrix = {label: {column: 0 for column in (*LABELS, "__failure__")} for label in LABELS}
    correct = failed = missing = 0
    for case in cases:
        prediction = by_id.get(case["id"])
        if prediction is None or prediction["status"] == "error":
            failed += 1
            missing += prediction is None
            matrix[case["gold"]]["__failure__"] += 1
        else:
            choice = prediction["choice"]
            matrix[case["gold"]][choice] += 1
            correct += choice == case["gold"]
    support = Counter(case["gold"] for case in cases)
    metrics = {}
    for label in LABELS:
        tp = matrix[label][label]
        fp = sum(matrix[other][label] for other in LABELS if other != label)
        fn = sum(count for column, count in matrix[label].items() if column != label)
        metrics[label] = {"support": support[label], "tp": tp, "fp": fp, "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else 0,
            "recall": tp / (tp + fn) if tp + fn else 0,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0}
    return {"sample_count": len(cases), "correct": correct, "accuracy": correct / len(cases),
        "macro_f1": sum(metrics[label]["f1"] for label in LABELS) / len(LABELS),
        "technical_failures": failed, "missing_predictions": missing,
        "technical_failure_rate": failed / len(cases), "per_class": metrics,
        "confusion_matrix": matrix,
        "metric_note": "All reviewed cases remain in denominators. Macro-F1 uses all four fixed labels; zero divisions are zero. needs_clarification is a class, not a technical failure."}
