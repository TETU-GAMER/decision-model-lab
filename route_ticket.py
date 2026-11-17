"""Route one ticket with an explicit candidate-order strategy, fully offline."""

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from importlib.metadata import version

from routing import CALL_COST, STRATEGIES, route_with_strategy
from run_example import MODEL_ID, ROOT, load_local_model, read_examples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", required=True, help="Ticket text; saved locally with all responses")
    parser.add_argument("--strategy", choices=STRATEGIES, default="cyclic4")
    args = parser.parse_args()
    if not args.text.strip():
        parser.error("Ticket text must not be empty")
    data = read_examples(ROOT / "examples.json")
    print(f"Strategy: {args.strategy}; planned local model calls: {CALL_COST[args.strategy]}", flush=True)
    model, lock, _, load_seconds = load_local_model("cpu")
    result = route_with_strategy(model.system_one, data, args.text, args.strategy)
    now = datetime.now(timezone.utc)
    record = {"created_at_utc": now.isoformat(), "model_id": MODEL_ID,
        "model_revision": lock["revision"], "model_load_seconds": load_seconds,
        "routing_sha256": hashlib.sha256((ROOT / "routing.py").read_bytes()).hexdigest(),
        "configuration_sha256": hashlib.sha256((ROOT / "examples.json").read_bytes()).hexdigest(),
        "environment": {"python": sys.version, "platform": platform.platform(),
            "device": str(next(model.parameters()).device), "dtype": str(next(model.parameters()).dtype),
            "packages": {name: version(name) for name in ("torch", "transformers", "safetensors", "huggingface_hub")}},
        "result": result}
    out = ROOT / "outputs" / ("ticket-" + now.strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "raw_calls"}, ensure_ascii=False, indent=2))
    print(f"Saved full request and responses: {out}")
    if result["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
