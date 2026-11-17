import json
import random
from pathlib import Path

from app.context.plan import build_plan

FIXTURES = Path(__file__).parent / "fixtures" / "thread_plans.json"


def plan_ids(plan):
    for item in plan:
        if isinstance(item, str):
            yield item
        else:
            for branch in item["merge"]:
                yield from plan_ids(branch["plan"])


def ancestors(parents, tip):
    seen = set()
    stack = [tip]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(parents[current])
    return seen


def test_shared_fixtures():
    for fixture in json.loads(FIXTURES.read_text(encoding="utf-8")):
        parents = fixture["parents"]
        order = {node: index for index, node in enumerate(fixture["order"])}
        assert build_plan(fixture["tip"], parents, order) == fixture["plan"], fixture["name"]


def test_generated_dags_include_each_ancestor_once_and_are_deterministic():
    rng = random.Random(12)
    parents = {"r": []}
    leaves = ["r"]
    for index in range(1, 80):
        node = f"n{index}"
        if len(leaves) > 1 and rng.random() < 0.35:
            first, second = rng.sample(leaves, 2)
            leaves.remove(first)
            leaves.remove(second)
            parents[node] = [first, second]
        else:
            parent = rng.choice(leaves)
            leaves.remove(parent)
            parents[node] = [parent]
        leaves.append(node)

    order = {node: index for index, node in enumerate(parents)}
    for tip in parents:
        first = build_plan(tip, parents, order)
        assert first == build_plan(tip, parents, order)
        actual = list(plan_ids(first))
        assert len(actual) == len(set(actual))
        assert set(actual) == ancestors(parents, tip)
