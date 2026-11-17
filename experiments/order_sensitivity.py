"""Label-free candidate-order probe: 24 permutations and one repeat per case."""

import argparse
import hashlib
import itertools
import json
import math
import platform
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from run_example import MODEL_ID, ROOT, load_local_model


def read_probe(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if data.get("purpose") != "ai_authored_exploratory_development_probe_not_a_benchmark":
        raise ValueError("Probe purpose must explicitly disclose exploratory AI authorship")
    criteria = data["criteria"]
    if not isinstance(criteria, dict) or len(criteria) != 4:
        raise ValueError("This experiment requires exactly four named candidates")
    if not all(isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip()
               for k, v in criteria.items()):
        raise ValueError("Candidate IDs and descriptions must be nonempty strings")
    if not isinstance(data["instructions"], str) or not data["instructions"].strip():
        raise ValueError("Instructions must be nonempty text")
    cases = data["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("Need at least one case")
    ids = set()
    for case in cases:
        if not isinstance(case["id"], str) or not case["id"].strip() or case["id"] in ids:
            raise ValueError("Case IDs must be nonempty and unique")
        ids.add(case["id"])
        if not isinstance(case["state"], str) or not case["state"].strip():
            raise ValueError("Each case needs nonempty state text")
    return data


def build_request(data, case, order):
    if len(order) != len(data["criteria"]) or set(order) != set(data["criteria"]):
        raise ValueError("Order must contain every candidate exactly once")
    # Only state, instructions and candidate IDs/descriptions reach the model.
    return {"state": case["state"], "questions": {"route": {
        "type": "choice", "instructions": data["instructions"],
        "criteria": {key: data["criteria"][key] for key in order},
    }}}


def validate_response(response, candidates):
    route = response["answers"]["route"]
    if route.get("error") or route.get("type") != "choice":
        raise ValueError(f"Model route error: {route.get('error', 'wrong type')}")
    probabilities = route["probabilities"]
    if set(probabilities) != set(candidates) or route["choice"] not in candidates:
        raise ValueError("Model response has incorrect candidate IDs")
    if any(isinstance(p, bool) or not isinstance(p, (int, float)) or
           not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities.values()):
        raise ValueError("Invalid candidate probability")
    if not math.isclose(sum(probabilities.values()), 1, rel_tol=0, abs_tol=2e-5):
        raise ValueError("Candidate probabilities do not sum to one")
    if probabilities[route["choice"]] != max(probabilities.values()):
        raise ValueError("Reported choice does not have the highest probability")
    return route


def total_variation(left, right, candidates):
    """Align by candidate ID, never by JSON insertion position."""
    return sum(abs(left[key] - right[key]) for key in candidates) / 2


def summarize(records, cases, candidates, expected_permutations=24):
    rows = []
    changed_comparisons = valid_comparisons = planned_comparisons = 0
    invalid_permutations = repeat_valid = repeat_agree = 0
    for case in cases:
        calls = [r for r in records if r["case_id"] == case["id"]]
        permutations = [r for r in calls if r["kind"] == "permutation"]
        valid = [r for r in permutations if r["status"] == "ok"]
        invalid_permutations += len(permutations) - len(valid)
        canonical = next((r for r in valid if r["order_index"] == 0), None)
        repeat = next((r for r in calls if r["kind"] == "canonical_repeat"), None)
        choices = Counter(r["response"]["answers"]["route"]["choice"] for r in valid)
        complete = (len(permutations) == expected_permutations and
                    len(valid) == expected_permutations and canonical is not None and
                    len({r["order_index"] for r in permutations}) == expected_permutations)
        planned_comparisons += expected_permutations - 1
        drifts = []
        if canonical:
            base = canonical["response"]["answers"]["route"]
            for record in valid:
                current = record["response"]["answers"]["route"]
                drifts.append(total_variation(base["probabilities"], current["probabilities"], candidates))
                if record["order_index"] != 0:
                    valid_comparisons += 1
                    changed_comparisons += current["choice"] != base["choice"]
        repeat_same = repeat_drift = None
        if canonical and repeat and repeat["status"] == "ok":
            again = repeat["response"]["answers"]["route"]
            repeat_same = again["choice"] == base["choice"]
            repeat_drift = total_variation(base["probabilities"], again["probabilities"], candidates)
            repeat_valid += 1
            repeat_agree += repeat_same
        rows.append({
            "case_id": case["id"], "scenario_tag": case.get("scenario_tag"),
            "state": case["state"], "complete": complete,
            "valid_permutations": len(valid), "choice_counts": dict(choices),
            "observed_choice_change": len(choices) > 1,
            "stable_across_all_orders": len(choices) == 1 if complete else None,
            "canonical_choice": base["choice"] if canonical else None,
            "max_tv_from_canonical": max(drifts) if drifts else None,
            "repeat_same_choice": repeat_same, "repeat_tv": repeat_drift,
        })
    complete_rows = [row for row in rows if row["complete"]]
    repeat_drifts = [row["repeat_tv"] for row in rows if row["repeat_tv"] is not None]
    order_drifts = [row["max_tv_from_canonical"] for row in rows if row["max_tv_from_canonical"] is not None]
    return {
        "case_count": len(cases), "complete_cases": len(complete_rows),
        "cases_with_observed_choice_change": sum(row["observed_choice_change"] for row in rows),
        "stable_complete_cases": sum(row["stable_across_all_orders"] for row in complete_rows),
        "planned_calls": len(cases) * (expected_permutations + 1),
        "recorded_calls": len(records),
        "invalid_calls": sum(record["status"] != "ok" for record in records),
        "invalid_permutation_calls": invalid_permutations,
        "planned_noncanonical_comparisons": planned_comparisons,
        "valid_noncanonical_comparisons": valid_comparisons,
        "changed_noncanonical_choices": changed_comparisons,
        "changed_choice_fraction_of_valid_comparisons": (
            changed_comparisons / valid_comparisons if valid_comparisons else None),
        "repeat_valid_pairs": repeat_valid, "repeat_choice_agreements": repeat_agree,
        "max_repeat_tv": max(repeat_drifts) if repeat_drifts else None,
        "max_order_tv": max(order_drifts) if order_drifts else None,
        "cases": rows,
    }


def render_report(summary, metadata):
    changed = summary["cases_with_observed_choice_change"]
    n = summary["case_count"]
    lines = [
        "# 候选顺序敏感性探索实验 v1", "",
        "本报告由实际保存的模型响应计算。样例为 AI 构造的探索开发材料，未由用户独立审核；没有 gold 标签，不报告分类准确率。", "",
        "## 设计与来源", "",
        f"- 模型：`{metadata['model_id']}`，revision `{metadata['model_revision']}`。",
        f"- 数据 SHA256：`{metadata['data_sha256']}`。",
        f"- {n} 条新工单，各枚举 4 个候选的 24 种排列，并在每条末尾重复原始排列；只改变候选排列，不改变文字、指令或权重。",
        "- 英文工单；场景标签仅说明覆盖意图，不作为模型输入或正确答案。原三条教学例未复用。",
        "- CPU / FP32；没有网络推理、付费 API、训练或微调。完整请求与响应见 `requests.jsonl`。", "",
        "## 实际结果", "",
        f"- 计划 {summary['planned_calls']} 次，保存 {summary['recorded_calls']} 次；错误或无效响应 {summary['invalid_calls']} 次。",
        f"- 完整有效样例 {summary['complete_cases']}/{n}；观察到选择变化的样例 {changed}/{n}。",
        f"- 完整样例中，所有排列选择一致的有 {summary['stable_complete_cases']} 条。",
        f"- 非原始排列：{summary['changed_noncanonical_choices']} 次选择变化 / {summary['valid_noncanonical_comparisons']} 次有效比较；计划比较 {summary['planned_noncanonical_comparisons']} 次。",
        f"- 重复对照：{summary['repeat_choice_agreements']}/{summary['repeat_valid_pairs']} 对选择一致，最大重复概率分布差异（TV）为 {summary['max_repeat_tv']}。",
        f"- 调换顺序后的最大概率分布差异（TV）为 {summary['max_order_tv']}。", "",
        "TV 为按候选 ID 对齐后各概率绝对差之和的一半，范围 0～1。重复对照不计入 24 种排列的统计。缺失或无效结果不算稳定，错误保留在分母说明中。", "",
        "## 逐条观察", "",
    ]
    for row in summary["cases"]:
        state = "选择变化" if row["observed_choice_change"] else (
            "所有排列选择相同" if row["complete"] else "结果不完整")
        lines.append(f"- `{row['case_id']}`：{state}；选择次数 {row['choice_counts']}；最大 TV={row['max_tv_from_canonical']}。")
    lines += ["", "## 能说什么与不能说什么", "",
        f"本次仅能描述这 {n} 条固定输入、该模型版本和当前 CPU 实现下的顺序影响。即使重复对照一致，也不能证明其他硬件或所有输入都确定性一致。",
        "没有人工独立标注或外部测试集，不能据此宣称分类准确率、上线收益、研究方法创新或性能提升。混合诉求的路由规范仍需用户确定。", "",
        "## 当前项目经历表述草稿", "",
        f"基于公开 0.6B 决策模型构建可复现的工单路由实验，固定模型、依赖和数据版本；对 {n} 条 AI 构造开发样例执行全部候选排列及重复对照，共记录 {summary['recorded_calls']} 次本地推理，分析选择变化与概率分布漂移，保留逐请求结果和失败信息。", "",
        "以上描述的是 AI 辅助实现的项目阶段；理解并能解释设计、指标与局限后再用于简历，不将其写成自主训练基础模型或独立完成全部实现。", "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/order_probe_v1.json")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    data = read_probe(args.data)
    orders = list(itertools.permutations(data["criteria"]))
    planned = len(data["cases"]) * (len(orders) + 1)
    if args.validate_only:
        print(f"Validated {len(data['cases'])} exploratory cases, {len(orders)} orders, {planned} planned calls; no model loaded.")
        return
    out = args.output_dir or ROOT / "outputs" / datetime.now(timezone.utc).strftime("order-probe-%Y%m%dT%H%M%S%fZ")
    if out.exists():
        parser.error("Output directory already exists; keep earlier results and choose a new directory")
    out.mkdir(parents=True)
    model, lock, _, load_seconds = load_local_model("cpu")
    import torch

    metadata = {
        "schema_version": 1, "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_id": MODEL_ID, "model_revision": lock["revision"],
        "data_file": args.data.name, "data_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
        "data_purpose": data["purpose"], "authorship": data["authorship"],
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "loader_sha256": hashlib.sha256((ROOT / "run_example.py").read_bytes()).hexdigest(),
        "candidate_ids": list(data["criteria"]), "case_count": len(data["cases"]),
        "orders_per_case": len(orders), "canonical_repeats_per_case": 1,
        "planned_calls": planned, "model_load_seconds": load_seconds,
        "environment": {"python": sys.version, "platform": platform.platform(),
            "device": str(next(model.parameters()).device), "dtype": str(next(model.parameters()).dtype),
            "torch_threads": torch.get_num_threads(),
            "packages": {name: version(name) for name in (
                "torch", "transformers", "safetensors", "huggingface_hub", "tokenizers")}},
    }
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (out / "dataset.json").write_bytes(args.data.read_bytes())
    records = []
    started = time.perf_counter()
    with (out / "requests.jsonl").open("w", encoding="utf-8") as stream:
        for case in data["cases"]:
            for index, order in enumerate([*orders, orders[0]]):
                record = {"case_id": case["id"],
                    "kind": "permutation" if index < len(orders) else "canonical_repeat",
                    "order_index": index, "candidate_order": list(order),
                    "request": build_request(data, case, order)}
                tick = time.perf_counter()
                try:
                    record["response"] = model.system_one(**record["request"])
                    validate_response(record["response"], data["criteria"])
                    record["status"] = "ok"
                except Exception as exc:
                    record.update(status="error", error_type=type(exc).__name__, error=str(exc))
                record["inference_seconds"] = time.perf_counter() - tick
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                stream.flush()
                records.append(record)
            print(f"Completed {case['id']}: {len(records)}/{planned} calls", flush=True)
    metadata["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    metadata["experiment_seconds_excluding_load"] = time.perf_counter() - started
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    summary = summarize(records, data["cases"], list(data["criteria"]), len(orders))
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "report.md").write_text(render_report(summary, metadata), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "cases"}, indent=2))
    print(f"Saved full experiment: {out}", flush=True)
    if summary["invalid_calls"] or summary["recorded_calls"] != planned:
        raise SystemExit("Experiment contains failures; retained full records, do not describe it as fully successful")


if __name__ == "__main__":
    main()
