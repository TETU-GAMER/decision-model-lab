import copy
import itertools
import json
import unittest
from collections import Counter

from experiments.compare_routing_strategies import analyze_pool
from experiments.order_sensitivity import build_request, read_probe
from routing import aggregate_routes, candidate_orders, route_with_strategy
from run_example import ROOT


DATA = {"instructions": "Choose a department", "criteria": {key: key for key in "abcd"},
        "cases": [{"id": "one", "state": "A fixed ticket"}]}


def route_for(order, winner):
    probabilities = {key: .7 if key == winner else .1 for key in order}
    return {"type": "choice", "choice": winner, "probabilities": probabilities}


def make_pool(adjacency=False):
    case = DATA["cases"][0]
    orders = list(itertools.permutations(DATA["criteria"]))
    records = []
    for index, order in enumerate([*orders, orders[0]]):
        winner = order[0]
        if adjacency:
            winner = "a" if order[(order.index("a") + 1) % 4] == "b" else "b"
        records.append({"case_id": "one", "order_index": index,
            "kind": "permutation" if index < 24 else "canonical_repeat",
            "candidate_order": list(order), "status": "ok",
            "request": build_request(DATA, case, order),
            "response": {"answers": {"route": route_for(order, winner)}}})
    return records


class RoutingStrategyTests(unittest.TestCase):
    def test_cyclic_orders_balance_every_position(self):
        orders = candidate_orders("dcab", "cyclic4")
        self.assertEqual(len(set(orders)), 4)
        for position in range(4):
            self.assertEqual(Counter(order[position] for order in orders), Counter("abcd"))

    def test_sorted_order_does_not_depend_on_incoming_order(self):
        for incoming in itertools.permutations("abcd"):
            self.assertEqual(candidate_orders(incoming, "sorted"), [("a", "b", "c", "d")])

    def test_cyclic_orbits_are_six_groups_not_one(self):
        groups = {frozenset(candidate_orders(order, "cyclic4")) for order in itertools.permutations("abcd")}
        self.assertEqual(len(groups), 6)

    def test_average_aligns_ids_and_ensemble_ties_are_deterministic(self):
        left = {"type": "choice", "choice": "a", "probabilities": {"a": .9, "b": .1}}
        right = {"type": "choice", "choice": "b", "probabilities": {"b": .8, "a": .2}}
        result = aggregate_routes([left, right], ["b", "a"])
        self.assertAlmostEqual(result["probabilities"]["a"], .55)
        self.assertEqual(result["choice"], "a")
        tied = {"type": "choice", "choice": "b", "probabilities": {"b": .5, "a": .5}}
        self.assertEqual(aggregate_routes([tied], ["b", "a"])["choice"], "b")
        self.assertEqual(aggregate_routes([tied, tied], ["b", "a"])["choice"], "a")
        with self.assertRaises(ValueError):
            aggregate_routes([], ["a", "b"])

    def test_failed_subcall_blocks_partial_aggregation(self):
        count = 0

        def predict(**request):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError("simulated unavailable call")
            order = list(request["questions"]["route"]["criteria"])
            return {"answers": {"route": route_for(order, order[0])}}

        result = route_with_strategy(predict, DATA, "ticket", "cyclic4")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["model_calls"], 4)
        self.assertEqual(result["successful_calls"], 3)
        self.assertNotIn("choice", result)
        self.assertEqual(len(result["raw_calls"]), 4)

    def test_replay_detects_simple_position_bias_and_call_costs(self):
        summary, _ = analyze_pool(DATA, make_pool())
        self.assertEqual(summary["strategies"]["single"]["cases_with_choice_change"], 1)
        for strategy in ["sorted", "cyclic4", "all24"]:
            self.assertEqual(summary["strategies"][strategy]["cases_with_choice_change"], 0)
        self.assertEqual(summary["strategies"]["cyclic4"]["model_calls_per_new_ticket"], 4)
        self.assertEqual(summary["strategies"]["all24"]["model_calls_per_new_ticket"], 24)

    def test_four_rotations_do_not_guarantee_arbitrary_order_invariance(self):
        summary, _ = analyze_pool(DATA, make_pool(adjacency=True))
        self.assertEqual(summary["strategies"]["cyclic4"]["cases_with_choice_change"], 1)
        self.assertEqual(summary["strategies"]["all24"]["cases_with_choice_change"], 0)

    def test_bad_source_pool_is_rejected_instead_of_dropping_records(self):
        for mutation in ["failure", "duplicate", "request", "repeat"]:
            records = copy.deepcopy(make_pool())
            if mutation == "failure":
                records[0]["status"] = "error"
            elif mutation == "duplicate":
                records[1] = copy.deepcopy(records[0])
            elif mutation == "request":
                records[0]["request"]["state"] = "different text"
            else:
                records[-1]["candidate_order"] = records[1]["candidate_order"]
                records[-1]["request"] = records[1]["request"]
            with self.assertRaises(ValueError, msg=mutation):
                analyze_pool(DATA, records)

    def test_fresh_batch_is_distinct_and_uses_the_same_task(self):
        fresh = read_probe(ROOT / "data/order_probe_prospective_v1.json")
        old = read_probe(ROOT / "data/order_probe_v1.json")
        teaching = json.loads((ROOT / "examples.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(fresh["criteria"], old["criteria"])
        self.assertEqual(fresh["instructions"], old["instructions"])
        previous = {case["state"] for case in old["cases"] + teaching["examples"]}
        self.assertFalse(previous & {case["state"] for case in fresh["cases"]})


if __name__ == "__main__":
    unittest.main()
