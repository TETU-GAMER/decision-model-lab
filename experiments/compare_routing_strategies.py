"""Replay a complete permutation pool to compare fixed routing strategies."""

import argparse
import hashlib
import itertools
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from experiments.order_sensitivity import build_request, total_variation, validate_response
from routing import CALL_COST, STRATEGIES, aggregate_routes, candidate_orders
from run_example import ROOT


def analyze_pool(data, records):
    ids = list(data["criteria"])
    orders = list(itertools.permutations(ids))
    expected = set(orders)
    case_ids = {case["id"] for case in data["cases"]}
    if any(record["case_id"] not in case_ids for record in records):
        raise ValueError("Unexpected case ID in source records")
    per_case = []
    for case in data["cases"]:
        calls = [r for r in records if r["case_id"] == case["id"]]
        perms = [r for r in calls if r["kind"] == "permutation"]
        repeats = [r for r in calls if r["kind"] == "canonical_repeat"]
        if len(perms) != 24 or len(repeats) != 1 or len(calls) != 25:
            raise ValueError(f"{case['id']}: require 24 permutations and one repeat; no dropped calls")
        pool = {}
        for call in calls:
            order = tuple(call["candidate_order"])
            if call["status"] != "ok" or order not in expected:
                raise ValueError(f"{case['id']}: failed or invalid source call")
            if call["request"] != build_request(data, case, order):
                raise ValueError(f"{case['id']}: source request differs from the fixed dataset")
            if list(call["request"]["questions"]["route"]["criteria"]) != list(order):
                raise ValueError(f"{case['id']}: request order does not match the recorded order")
            validate_response(call["response"], ids)
            if call["kind"] == "permutation":
                if order in pool:
                    raise ValueError(f"{case['id']}: duplicate source permutation")
                pool[order] = call
        if set(pool) != expected:
            raise ValueError(f"{case['id']}: missing source permutation")
        if tuple(repeats[0]["candidate_order"]) != tuple(ids):
            raise ValueError(f"{case['id']}: repeat does not use the canonical order")
        base_route = pool[tuple(ids)]["response"]["answers"]["route"]
        repeat_route = repeats[0]["response"]["answers"]["route"]
        reference = aggregate_routes([pool[order]["response"]["answers"]["route"] for order in orders], ids)
        outcomes = {}
        for strategy in STRATEGIES:
            variants = []
            for incoming in orders:
                used = candidate_orders(incoming, strategy)
                routes = [pool[order]["response"]["answers"]["route"] for order in used]
                answer = aggregate_routes(routes, ids)
                variants.append({"incoming_order": list(incoming),
                    "source_orders": [list(order) for order in used], **answer,
                    "tv_to_full24_mean": total_variation(answer["probabilities"], reference["probabilities"], ids)})
            base = variants[0]
            counts = Counter(variant["choice"] for variant in variants)
            outcomes[strategy] = {"choice_counts": dict(counts),
                "changed_with_incoming_order": len(counts) > 1,
                "changed_noncanonical_choices": sum(v["choice"] != base["choice"] for v in variants[1:]),
                "max_tv_from_canonical": max(total_variation(v["probabilities"], base["probabilities"], ids) for v in variants),
                "agreements_with_full24_mean": sum(v["choice"] == reference["choice"] for v in variants),
                "max_tv_to_full24_mean": max(v["tv_to_full24_mean"] for v in variants),
                "variants": variants}
        per_case.append({"case_id": case["id"], "state": case["state"],
                         "repeat_choice_agreement": base_route["choice"] == repeat_route["choice"],
                         "repeat_tv": total_variation(base_route["probabilities"], repeat_route["probabilities"], ids),
                         "full24_mean_reference": reference, "strategies": outcomes})
    n = len(per_case)
    summary = {"case_count": n, "source_calls": len(records),
        "incoming_orders_per_case": 24, "noncanonical_comparisons": n * 23,
        "strategy_variants": n * 24,
        "source_repeat_choice_agreements": sum(case["repeat_choice_agreement"] for case in per_case),
        "source_repeat_max_tv": max(case["repeat_tv"] for case in per_case),
        "comparison_type": "Replay of saved responses; no new model calls or end-to-end latency measurements.",
        "strategies": {}}
    for strategy in STRATEGIES:
        outcomes = [case["strategies"][strategy] for case in per_case]
        summary["strategies"][strategy] = {
            "model_calls_per_new_ticket": CALL_COST[strategy],
            "cases_with_choice_change": sum(row["changed_with_incoming_order"] for row in outcomes),
            "changed_noncanonical_choices": sum(row["changed_noncanonical_choices"] for row in outcomes),
            "max_tv_from_canonical": max(row["max_tv_from_canonical"] for row in outcomes),
            "agreements_with_full24_mean": sum(row["agreements_with_full24_mean"] for row in outcomes),
            "max_tv_to_full24_mean": max(row["max_tv_to_full24_mean"] for row in outcomes)}
    return summary, per_case


def render_report(summary):
    lines = ["# 路由策略对照", "",
        "从完整的候选排列响应池回放计算；没有为每个策略重新调用模型，也不比较端到端速度。", "",
        "## 方法", "",
        "- single：使用输入候选顺序，调用一次。",
        "- sorted：按候选 ID 固定排序，调用一次。输入被固定，因此输出对外部排列保持不变是预期性质。",
        "- cyclic4：使用输入顺序的四次循环轮换，按部门 ID 对齐后平均概率，每个部门各占一次每个位置，调用四次。",
        "- all24：平均全部排列的概率，调用 24 次。对外部排列不变是构造性质，作为计算参考，不是正确答案。", "",
        "## 结果", "",
        f"共 {summary['case_count']} 条工单，每种策略比较每条的 24 种外部输入排列。",
        f"原始调用重复对照：{summary['source_repeat_choice_agreements']}/{summary['case_count']} 对选择一致，最大 TV={summary['source_repeat_max_tv']}。", ""]
    for strategy, metrics in summary["strategies"].items():
        lines.append(f"- {strategy}：{metrics['cases_with_choice_change']}/{summary['case_count']} 条出现改选；非原始排列改选 {metrics['changed_noncanonical_choices']}/{summary['noncanonical_comparisons']} 次；最大 TV={metrics['max_tv_from_canonical']}；每条新工单需 {metrics['model_calls_per_new_ticket']} 次调用。")
    lines += ["", "## 实验范围", "",
        "这批样例没有独立真值，只比较顺序稳定性。固定排序或全排列平均得到零改选，并不能证明分类正确。",
        "cyclic4 对循环轮换使用相同的四个排列，但对所有 24 种排列只形成六组；它并不保证对任意排列不变。",
        "与全排列均值的接近程度只衡量近似关系，不是准确率。概率和聚合后的差值均未校准。",
        "调用次数是部署成本口径，不能直接换算成实测延迟。原始响应池只计算过每个排列一次。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    source = args.run_dir
    data = json.loads((source / "dataset.json").read_text(encoding="utf-8-sig"))
    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    if hashlib.sha256((source / "dataset.json").read_bytes()).hexdigest() != metadata["data_sha256"]:
        raise ValueError("Source dataset hash mismatch")
    records = [json.loads(line) for line in (source / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
    summary, cases = analyze_pool(data, records)
    out = args.output_dir or ROOT / "outputs" / datetime.now(timezone.utc).strftime("strategy-replay-%Y%m%dT%H%M%S%fZ")
    if out.exists():
        parser.error("Output directory already exists")
    out.mkdir(parents=True)
    provenance = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_id": metadata["model_id"], "model_revision": metadata["model_revision"],
        "source_data_sha256": metadata["data_sha256"],
        "source_metadata_sha256": hashlib.sha256((source / "metadata.json").read_bytes()).hexdigest(),
        "source_requests_sha256": hashlib.sha256((source / "requests.jsonl").read_bytes()).hexdigest(),
        "routing_sha256": hashlib.sha256((ROOT / "routing.py").read_bytes()).hexdigest(),
        "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_call_count": len(records), "new_model_calls_for_replay": 0}
    for name, content in [("summary.json", summary), ("cases.json", cases), ("metadata.json", provenance)]:
        (out / name).write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "report.md").write_text(render_report(summary), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Saved comparison: {out}")


if __name__ == "__main__":
    main()
