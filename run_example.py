"""Run one teaching example. --validate-only stays fully offline."""

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MODEL_ID = "vllm-sr/Decision-1.0-Kai-0.6B"


def read_examples(path):
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    criteria = data["criteria"]
    if not isinstance(criteria, dict) or not criteria:
        raise ValueError("criteria must be a nonempty dictionary")
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in criteria.items()):
        raise ValueError("candidate IDs and descriptions must be strings")
    if not isinstance(data["instructions"], str) or not data["instructions"].strip():
        raise ValueError("instructions must be a nonempty string")
    examples = data["examples"]
    if not isinstance(examples, list) or not examples:
        raise ValueError("examples must be a nonempty list")
    seen = set()
    for row in examples:
        if not isinstance(row["id"], str) or row["id"] in seen:
            raise ValueError("example IDs must be unique strings")
        seen.add(row["id"])
        if not isinstance(row["state"], str) or not row["state"].strip():
            raise ValueError("each example needs nonempty state text")
        if row["intended_choice"] not in criteria:
            raise ValueError("intended_choice must refer to a candidate")
    return data


def load_local_model(device="cpu"):
    """Shared, offline loader; verify the pinned release before executing code."""
    lock = json.loads((ROOT / "model-lock.json").read_text(encoding="utf-8-sig"))
    model_path = ROOT / "models" / lock["revision"]
    if not (ROOT / "audit" / "download-verification.json").exists():
        raise RuntimeError("Run download_model.py first to download and verify the pinned release")
    verification = json.loads((ROOT / "audit/download-verification.json").read_text(encoding="utf-8"))
    if verification["revision"] != lock["revision"] or verification["model_id"] != lock["model_id"]:
        raise RuntimeError("Download verification belongs to a different model release")
    for entry in lock["files"]:
        path = model_path / entry["path"]
        if not path.is_file() or path.stat().st_size != entry["size"]:
            raise RuntimeError(f"Missing or changed model file: {entry['path']}")
        if entry["reviewed_source"]:
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
                raise RuntimeError(f"Custom code differs from the reviewed version: {entry['path']}")
    os.environ["HF_HOME"] = str(ROOT / ".cache" / "huggingface")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from transformers import AutoModel
    from transformers.dynamic_module_utils import get_cached_module_file

    # Transformers 4.57.6 copies only immediate imports for a local model.
    # Stage every hash-checked source so its recursive dependency scan also
    # finds the indirect ROCm helper. Upstream source files stay unchanged.
    for entry in lock["files"]:
        if entry["reviewed_source"]:
            get_cached_module_file(str(model_path), entry["path"], local_files_only=True)

    print(f"Loading verified local model on {device}...", flush=True)
    started = time.perf_counter()
    model = AutoModel.from_pretrained(
        str(model_path), trust_remote_code=True, device=device, local_files_only=True
    )
    load_seconds = time.perf_counter() - started
    return model, lock, model_path, load_seconds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--example-id", default="demo-001")
    parser.add_argument("--device", choices=["cpu", "cuda:0"], default="cpu")
    args = parser.parse_args()
    data = read_examples(ROOT / "examples.json")
    example = next((x for x in data["examples"] if x["id"] == args.example_id), None)
    if example is None:
        parser.error("unknown example ID")
    if args.validate_only:
        print(f"Validated {len(data['examples'])} teaching examples; no model call or network access.")
        return

    model, lock, model_path, load_seconds = load_local_model(args.device)
    import torch

    # The intended answer is deliberately excluded from the model request.
    request = {
        "state": example["state"],
        "questions": {"route": {
            "type": "choice", "instructions": data["instructions"],
            "criteria": data["criteria"],
        }},
    }
    print(f"Loaded in {load_seconds:.2f}s. Running {example['id']}...", flush=True)
    started = time.perf_counter()
    response = model.system_one(**request)
    inference_seconds = time.perf_counter() - started
    now = datetime.now(timezone.utc)
    record = {
        "created_at_utc": now.isoformat(),
        "model_id": MODEL_ID,
        "requested_revision": lock["revision"],
        "resolved_revision": lock["revision"],
        "model_source": str(model_path),
        "source_verification": "audit/download-verification.json",
        "device_requested": args.device,
        "device_actual": str(next(model.parameters()).device),
        "dtype_actual": str(next(model.parameters()).dtype),
        "environment": {
            "python": sys.version, "executable": sys.executable,
            "platform": platform.platform(), "torch_cuda_build": torch.version.cuda,
            "packages": {name: version(name) for name in (
                "torch", "transformers", "safetensors", "huggingface_hub", "tokenizers"
            )},
        },
        "example_id": example["id"],
        "data_purpose": data["purpose"],
        "request": request,
        "response": response,
        "load_seconds": load_seconds,
        "inference_seconds": inference_seconds,
        "note": "Single teaching example, not a benchmark or a measured improvement.",
    }
    output_dir = ROOT / "outputs"
    output_dir.mkdir(exist_ok=True)
    output = output_dir / f"{args.example_id}_{now.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    serialized = json.dumps(record, ensure_ascii=False, indent=2)
    output.write_text(serialized, encoding="utf-8")
    print(serialized)
    print(f"Saved: {output}")
    route = response.get("answers", {}).get("route", {})
    if route.get("error") or route.get("choice") not in data["criteria"]:
        raise RuntimeError("Model returned no valid route; full response was saved above")


if __name__ == "__main__":
    main()
