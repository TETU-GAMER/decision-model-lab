"""Prepare and review development cases; no model predictions are displayed."""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from run_example import ROOT
from task_policy import LABELS, fingerprint, load_policy, policy_hash, state_hash

DEFAULT_POLICY = ROOT / "data/task_policy_v1.json"
DEFAULT_QUEUE = ROOT / "data/review_queue_v1.json"
DEFAULT_LOCAL = ROOT / "local_review"
HOLDOUT_PURPOSE = "prospective_holdout_review_v1"
KEYS = {"b": "billing", "t": "technical", "d": "delivery", "c": "needs_clarification"}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def prepare_queue(policy, sources, reading_aid):
    items = []
    provenance = []
    seen = set()
    import hashlib
    for source in sources:
        source = Path(source)
        data = json.loads(source.read_text(encoding="utf-8-sig"))
        provenance.append({"file": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
        for case in data["cases"]:
            if case["id"] in seen:
                raise ValueError("Duplicate review case ID")
            seen.add(case["id"])
            items.append({"id": case["id"], "state": case["state"],
                "state_sha256": state_hash(case["state"]),
                "reading_aid_zh": reading_aid.get(case["id"]), "label": None, "reason": None})
    priority = {"order-003": 0, "fresh-004": 1, "fresh-009": 2}
    items.sort(key=lambda case: priority.get(case["id"], 3))
    return {"schema_version": 1, "purpose": "development_review_previously_probed_cases",
        "policy_id": policy["policy_id"], "policy_sha256": policy_hash(policy),
        "source_files": provenance,
        "note": "Previously probed AI-authored cases, not an independent test set. No model predictions or scenario tags are shown. Chinese text is an AI reading aid.",
        "items": items}


def load_review_state(queue_path, policy_path, local_dir):
    policy = load_policy(policy_path)
    queue_path = Path(queue_path)
    queue = json.loads(queue_path.read_text(encoding="utf-8-sig"))
    if queue["purpose"] not in ("development_review_previously_probed_cases", HOLDOUT_PURPOSE):
        raise ValueError("Unexpected review purpose")
    if queue["policy_id"] != policy["policy_id"] or queue["policy_sha256"] != policy_hash(policy):
        raise ValueError("任务规则已变化，请为新规则生成新的审核队列。")
    if not queue["items"] or len({row["id"] for row in queue["items"]}) != len(queue["items"]):
        raise ValueError("Review queue is empty or has duplicate IDs")
    for row in queue["items"]:
        if not isinstance(row["id"], str) or not row["id"].strip() or not isinstance(row["state"], str) or not row["state"].strip():
            raise ValueError("Review cases need nonempty IDs and text")
        if state_hash(row["state"]) != row["state_sha256"]:
            raise ValueError("Review text hash mismatch")
        if row.get("label") is not None or row.get("reason") is not None:
            raise ValueError("Keep the queue unchanged; save human labels in the local review file")
    queue_digest = fingerprint(queue)
    path = Path(local_dir) / "annotations.json"
    annotations = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {
        "schema_version": 1, "policy_sha256": policy_hash(policy), "queue_sha256": queue_digest, "reviews": []}
    if annotations["policy_sha256"] != policy_hash(policy) or annotations["queue_sha256"] != queue_digest:
        raise ValueError("已有标注与当前规则或队列不符，请用新的 local-dir 保留版本。")
    ids = {case["id"]: case for case in queue["items"]}
    seen = set()
    for review in annotations["reviews"]:
        if review["id"] not in ids or review["id"] in seen:
            raise ValueError("Unknown or duplicate annotation ID")
        seen.add(review["id"])
        if review["state_sha256"] != ids[review["id"]]["state_sha256"]:
            raise ValueError("Annotation belongs to changed text")
        if review["label"] not in LABELS or review.get("source") != "human_review":
            raise ValueError("Need an explicit human review record")
        if not all(isinstance(review.get(key), str) and review[key].strip()
                   for key in ("reviewer", "reviewed_at_utc")):
            raise ValueError("Review requires reviewer and time")
        label_only = queue["purpose"] == HOLDOUT_PURPOSE and review.get("assistance") == "user_label_only"
        if not (label_only and review.get("reason") is None):
            if not isinstance(review.get("reason"), str) or not review["reason"].strip():
                raise ValueError("Review requires a reason")
    return policy, queue, annotations


def review_status(queue, annotations):
    completed = {row["id"] for row in annotations["reviews"]}
    pending = [row["id"] for row in queue["items"] if row["id"] not in completed]
    return {"purpose": queue["purpose"], "total_cases": len(queue["items"]),
            "reviewed_cases": len(completed), "pending_case_ids": pending,
            "scoring_ready": not pending}


def add_review(annotations, case, label, reason, reviewer, *, allow_label_only=False):
    reason = reason.strip() if reason else None
    if label not in LABELS or (not reason and not allow_label_only) or not reviewer.strip():
        raise ValueError("Need a valid department, reason and reviewer alias")
    if any(row["id"] == case["id"] for row in annotations["reviews"]):
        raise ValueError("Case already reviewed; preserve earlier records")
    annotations["reviews"].append({"id": case["id"], "state_sha256": case["state_sha256"],
        "label": label, "reason": reason, "reviewer": reviewer.strip(),
        **({"assistance": "user_label_only"} if not reason else {}),
        "source": "human_review", "reviewed_at_utc": datetime.now(timezone.utc).isoformat()})


def annotate(policy, queue, annotations, local_dir, reviewer, limit, ask=input):
    allow_label_only = queue["purpose"] == HOLDOUT_PURPOSE
    print("本轮任务规则：")
    for rule in policy["rules_zh"]:
        print("- " + rule)
    print("\nb=账单，t=技术支持，d=配送，c=需要澄清，s=跳过，q=退出。每次保存后可随时退出。")
    completed = {row["id"] for row in annotations["reviews"]}
    count = 0
    for case in queue["items"]:
        if case["id"] in completed or count >= limit:
            continue
        print(f"\n{case['id']}: {case['state']}")
        if case.get("reading_aid_zh"):
            print("中文参考：" + case["reading_aid_zh"])
        while True:
            answer = ask("部门 [b/t/d/c/s/q]：").strip().lower()
            if answer == "q":
                return count
            if answer == "s":
                break
            if answer not in KEYS:
                print("请输入 b、t、d、c、s 或 q。")
                continue
            reason = ask("选择理由（可留空）：" if allow_label_only else "选择理由：").strip()
            if not reason and not allow_label_only:
                print("理由不能为空，此条尚未保存。")
                continue
            add_review(annotations, case, KEYS[answer], reason, reviewer, allow_label_only=allow_label_only)
            write_json(Path(local_dir) / "annotations.json", annotations)
            with (Path(local_dir) / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(annotations["reviews"][-1], ensure_ascii=False) + "\n")
            count += 1
            print("已保存。")
            break
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--local-dir", type=Path, default=DEFAULT_LOCAL)
    parser.add_argument("--reviewer", default="reviewer-1", help="Reviewer alias, not necessarily a real name")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("limit must be positive")
    if args.prepare:
        if args.queue.exists():
            parser.error("队列已存在，不能覆盖；请指定新的 --queue 路径。")
        policy = load_policy(args.policy)
        aid = json.loads((ROOT / "data/review_reading_aid_zh.json").read_text(encoding="utf-8"))["translations"]
        queue = prepare_queue(policy, [ROOT / "data/order_probe_v1.json", ROOT / "data/order_probe_prospective_v1.json"], aid)
        write_json(args.queue, queue)
    policy, queue, annotations = load_review_state(args.queue, args.policy, args.local_dir)
    if not args.status and not args.prepare:
        try:
            annotate(policy, queue, annotations, args.local_dir, args.reviewer, args.limit)
        except (EOFError, KeyboardInterrupt):
            print("\n审核结束，已完成的记录已保存。")
    print(json.dumps(review_status(queue, annotations), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
