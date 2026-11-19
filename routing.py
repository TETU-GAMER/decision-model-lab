"""Candidate-order strategies for the four-department routing experiment."""

import itertools
import math
import time
from collections import Counter

from experiments.order_sensitivity import build_request, validate_response

STRATEGIES = ("single", "sorted", "cyclic4", "all24")
CALL_COST = {"single": 1, "sorted": 1, "cyclic4": 4, "all24": 24}


def candidate_orders(candidate_ids, strategy):
    ids = list(candidate_ids)
    if len(ids) != 4 or len(set(ids)) != 4 or not all(isinstance(key, str) and key for key in ids):
        raise ValueError("Routing strategies require four distinct candidate IDs")
    if strategy == "single":
        return [tuple(ids)]
    if strategy == "sorted":
        return [tuple(sorted(ids))]
    if strategy == "cyclic4":
        return [tuple(ids[offset:] + ids[:offset]) for offset in range(4)]
    if strategy == "all24":
        return list(itertools.permutations(ids))
    raise ValueError(f"Unknown strategy: {strategy}")


def aggregate_routes(routes, candidate_ids):
    """Average by candidate ID; use lexical ID tie-breaking for ensembles."""
    if not routes:
        raise ValueError("Cannot aggregate an empty set of responses")
    keys = sorted(candidate_ids)
    for route in routes:
        validate_response({"answers": {"route": route}}, keys)
    probabilities = {
        key: math.fsum(route["probabilities"][key] for route in routes) / len(routes)
        for key in keys
    }
    choice = routes[0]["choice"] if len(routes) == 1 else max(keys, key=probabilities.__getitem__)
    top = sorted(probabilities.values(), reverse=True)
    return {"choice": choice, "probabilities": probabilities,
            "top_two_margin": top[0] - top[1],
            "vote_counts": dict(Counter(route["choice"] for route in routes))}


def run_choice_call(predict, data, state, order):
    """Capture one model call and return its validated route, if successful."""
    request = build_request(data, {"state": state}, order)
    call = {"candidate_order": list(order), "request": request}
    route = None
    started = time.perf_counter()
    try:
        call["response"] = predict(**request)
        route = validate_response(call["response"], data["criteria"])
        call["status"] = "ok"
    except Exception as error:
        call.update(status="error", error_type=type(error).__name__, error=str(error))
    call["inference_seconds"] = time.perf_counter() - started
    return call, route


def route_with_strategy(predict, data, state, strategy="cyclic4"):
    """Call an injected model predictor; any failed call blocks aggregation."""
    if not isinstance(state, str) or not state.strip():
        raise ValueError("Ticket text must not be empty")
    orders = candidate_orders(data["criteria"], strategy)
    calls = []
    routes = []
    for index, order in enumerate(orders):
        call, route = run_choice_call(predict, data, state, order)
        calls.append({"index": index, **call})
        if route is not None:
            routes.append(route)
    result = {"strategy": strategy, "model_calls": len(calls),
              "successful_calls": len(routes), "raw_calls": calls,
              "probability_note": "Uncalibrated mean model probabilities, not measured correctness."}
    if len(routes) != len(orders):
        result.update(status="error", error="At least one model call failed; no partial average returned")
        return result
    result.update(status="ok", **aggregate_routes(routes, data["criteria"]))
    return result
