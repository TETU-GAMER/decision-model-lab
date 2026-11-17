"""Version and bind the routing task separately from model versions."""
import hashlib
import json
from pathlib import Path

LABELS = ("billing", "technical", "delivery", "needs_clarification")


def fingerprint(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def state_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_policy(path):
    policy = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(policy.get("policy_id"), str) or not policy["policy_id"].strip():
        raise ValueError("Policy needs a nonempty version ID")
    if set(policy["criteria"]) != set(LABELS):
        raise ValueError("Policy must define the four routing labels")
    if not all(isinstance(v, str) and v.strip() for v in policy["criteria"].values()):
        raise ValueError("Candidate descriptions must be nonempty text")
    if not isinstance(policy["instructions"], str) or not policy["instructions"].strip():
        raise ValueError("Policy instructions must be nonempty text")
    if not isinstance(policy.get("rules_zh"), list) or not policy["rules_zh"] or not all(
            isinstance(rule, str) and rule.strip() for rule in policy["rules_zh"]):
        raise ValueError("Policy needs readable review rules")
    return policy


def policy_hash(policy):
    return fingerprint({key: policy[key] for key in ("policy_id", "instructions", "criteria", "rules_zh")})
