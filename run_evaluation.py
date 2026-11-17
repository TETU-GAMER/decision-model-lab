"""Evaluate reviewed development cases, with separate rule/model methods."""
import argparse
import hashlib
import json
import platform
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from importlib.metadata import version

from evaluation import ReviewPending, load_reviewed_cases, score_predictions
from review_cases import DEFAULT_LOCAL, DEFAULT_POLICY, DEFAULT_QUEUE, load_review_state, review_status, write_json
from routing import CALL_COST, STRATEGIES, route_with_strategy
from rule_baseline import route_by_rules
from run_example import MODEL_ID, ROOT, load_local_model
from task_policy import fingerprint, policy_hash

METHODS = ("rules", *STRATEGIES)


def annotation_provenance(annotations):
    reviews = annotations["reviews"]
    return {"label_count": len(reviews),
        "label_counts": dict(Counter(row["label"] for row in reviews)),
        "assistance_counts": dict(Counter(row.get("assistance", "user_label_and_reason") for row in reviews)),
        "ai_reasons_not_confirmed_by_user": sum(row.get("reason_confirmed_by_user") is False for row in reviews),
        "note": "User-provided or user-confirmed labels, including AI-assisted decisions; not independent blind annotation."}


def render_report(scores, metadata):
    n = metadata["sample_count"]
    provenance = metadata["annotation_provenance"]
    lines = ["# 开发集分类对照 v1", "",
        f"使用 {n} 条用户给出或确认标签的开发工单；任务规则为 `{metadata['policy_id']}`。",
        "样例由 AI 构造，已经用于此前的探索实验，部分标签参考过 AI 解释，本报告不作为独立测试结果。", "",
        "## 标注来源", "",
        f"- 类别分布：{provenance['label_counts']}。",
        f"- 辅助方式：{provenance['assistance_counts']}。",
        f"- 其中 {provenance['ai_reasons_not_confirmed_by_user']} 条的理由由 AI 补充且未经用户单独确认，类别由用户明确给出。", "",
        "## 实际结果", ""]
    for method, score in scores.items():
        lines.append(f"- {method}：匹配标签 {score['correct']}/{n}，准确率 {score['accuracy']:.2%}，Macro-F1={score['macro_f1']:.6f}，技术失败 {score['technical_failures']} 次。")
    lines += ["", "## 统计口径", "",
        "准确率保留全部样例作为分母。Macro-F1 对四个固定类别取平均，分母为零的项记 0。需要澄清是正常类别，技术失败或缺失预测单独计数。",
        "规则和三种模型方法使用同一任务定义。标签及审核理由不进入模型请求，旧任务指令下的预测没有混入本次评分。",
        "模型每条调用次数分别为 single=1、sorted=1、cyclic4=4；关键词规则不调用模型。记录中的耗时是本次观察，不作为受控速度基准。", "",
        "## 文件", "",
        "scores.json 保存完整分类指标及混淆矩阵；predictions.jsonl 保存每个方法的输出与原始模型子请求；metadata.json 保存模型、任务、数据和运行环境摘要。标注及审核理由另存于本机，不自动公开。", ""]
    return "\n".join(lines)


def evaluate_methods(predict, policy, cases, methods, on_record=None):
    if not methods or len(set(methods)) != len(methods) or set(methods) - set(METHODS):
        raise ValueError("Methods must be nonempty, known and unique")
    if predict is None and any(method != "rules" for method in methods):
        raise ValueError("Model methods require a predictor")
    records = []
    for case in cases:
        for method in methods:
            tick = time.perf_counter()
            row = {"id": case["id"], "method": method}
            try:
                detail = route_by_rules(case["state"]) if method == "rules" else route_with_strategy(
                    predict, policy, case["state"], method)
                row.update(status=detail.get("status", "ok"), detail=detail,
                           choice=detail.get("choice"), model_calls=detail["model_calls"])
                if row["status"] != "ok":
                    row["choice"] = None
                    row["error"] = detail["error"]
            except Exception as error:
                row.update(status="error", choice=None, model_calls=0,
                           error_type=type(error).__name__, error=str(error))
            row["elapsed_seconds"] = time.perf_counter() - tick
            records.append(row)
            if on_record is not None:
                on_record(row)
    scores = {method: score_predictions(cases, [row for row in records if row["method"] == method])
              for method in methods}
    return records, scores


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--local-dir", type=Path, default=DEFAULT_LOCAL)
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=["rules", "single", "sorted", "cyclic4"])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    if len(set(args.methods)) != len(args.methods):
        parser.error("Methods must not be repeated")
    policy, queue, annotations = load_review_state(args.queue, args.policy, args.local_dir)
    status = review_status(queue, annotations)
    status["policy_id"] = policy["policy_id"]
    status["planned_model_calls_if_ready"] = len(queue["items"]) * sum(CALL_COST.get(method, 0) for method in args.methods)
    if args.validate_only:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0 if status["scoring_ready"] else 2
    try:
        policy, queue, annotations, cases = load_reviewed_cases(args.queue, args.policy, args.local_dir)
    except ReviewPending as error:
        print(str(error))
        print("先运行 review_cases.py；已完成的审核会在下次继续使用。")
        return 2
    out = args.output_dir or ROOT / "outputs" / datetime.now(timezone.utc).strftime("evaluation-%Y%m%dT%H%M%S%fZ")
    if out.exists():
        parser.error("Output directory already exists")
    out.mkdir(parents=True)
    model = None
    lock = None
    load_seconds = 0
    if any(method != "rules" for method in args.methods):
        model, lock, _, load_seconds = load_local_model("cpu")
    environment = {"python": sys.version, "platform": platform.platform()}
    if model is not None:
        import torch
        environment.update(device=str(next(model.parameters()).device),
            dtype=str(next(model.parameters()).dtype), torch_threads=torch.get_num_threads(),
            packages={name: version(name) for name in ("torch", "transformers", "safetensors", "huggingface_hub", "tokenizers")})
    metadata = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": queue["purpose"], "policy_id": policy["policy_id"], "policy_sha256": policy_hash(policy),
        "queue_sha256": annotations["queue_sha256"], "annotations_sha256": fingerprint(annotations),
        "model_id": MODEL_ID if model is not None else None,
        "model_revision": lock["revision"] if lock else None, "model_load_seconds": load_seconds,
        "methods": args.methods, "sample_count": len(cases),
        "annotation_provenance": annotation_provenance(annotations),
        "environment": environment,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scorer_sha256": hashlib.sha256((ROOT / "evaluation.py").read_bytes()).hexdigest(),
        "rules_sha256": hashlib.sha256((ROOT / "rule_baseline.py").read_bytes()).hexdigest(),
        "note": "Reviewed development cases previously used in model exploration; not an independent test result."}
    write_json(out / "metadata.json", metadata)
    write_json(out / "annotations.json", annotations)
    write_json(out / "reviewed_cases.json", {"cases": cases})
    with (out / "predictions.jsonl").open("w", encoding="utf-8") as stream:
        def save_record(row):
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
        records, scores = evaluate_methods(model.system_one if model is not None else None,
                                           policy, cases, args.methods, save_record)
    write_json(out / "scores.json", scores)
    (out / "report.md").write_text(render_report(scores, metadata), encoding="utf-8")
    print(json.dumps({method: {key: result[key] for key in (
        "sample_count", "accuracy", "macro_f1", "technical_failure_rate")}
        for method, result in scores.items()}, indent=2))
    print(f"Saved development evaluation: {out}")
    return 1 if any(row["status"] != "ok" for row in records) else 0


if __name__ == "__main__":
    sys.exit(main())
