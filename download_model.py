"""Download the reviewed, pinned release; do not execute its custom code."""

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ["HF_HOME"] = str(ROOT / ".cache" / "huggingface")
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_XET"] = "1"


def main():
    from huggingface_hub import snapshot_download

    lock = json.loads((ROOT / "model-lock.json").read_text(encoding="utf-8-sig"))
    target = ROOT / "models" / lock["revision"]
    snapshot_download(
        lock["model_id"], revision=lock["revision"], local_dir=target,
        allow_patterns=[entry["path"] for entry in lock["files"]], max_workers=2,
    )
    verified = []
    for entry in lock["files"]:
        path = target / entry["path"]
        if path.stat().st_size != entry["size"]:
            raise ValueError(f"File size mismatch: {entry['path']}")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if entry["sha256"] and digest != entry["sha256"]:
            raise ValueError(f"SHA256 mismatch: {entry['path']}")
        verified.append({"path": entry["path"], "sha256": digest})
    record = {"model_id": lock["model_id"], "revision": lock["revision"], "files": verified}
    audit_dir = ROOT / "audit"
    audit_dir.mkdir(exist_ok=True)
    (audit_dir / "download-verification.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8"
    )
    print(f"Verified {len(verified)} files. Custom model code was not executed.")
    print(f"Local model: {target}")


if __name__ == "__main__":
    main()
