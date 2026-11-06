from functools import lru_cache
from typing import Any, Callable, Mapping, Sequence


PlanItem = str | dict[str, list[dict[str, Any]]]


def build_plan(
    tip: str,
    parents: Mapping[str, Sequence[str]],
    order: Mapping[str, Any] | Callable[[str], Any],
) -> list[PlanItem]:
    """Build a deterministic reading plan containing every ancestor exactly once."""
    order_key = order if callable(order) else order.__getitem__

    @lru_cache(None)
    def ancestors(node: str) -> frozenset[str]:
        return frozenset({node}).union(*(ancestors(parent) for parent in parents[node]))

    def thread(node: str, done: frozenset[str]) -> list[PlanItem]:
        if node in done:
            return []
        node_parents = parents[node]
        if not node_parents:
            return [node]
        prefix = thread(node_parents[0], done) if len(node_parents) == 1 else join(node_parents, done)
        return prefix + [node]

    def join(tips: Sequence[str], done: frozenset[str]) -> list[PlanItem]:
        common = frozenset.intersection(*(ancestors(tip) for tip in tips)) - done
        heads = sorted(
            (card for card in common if not any(card != other and card in ancestors(other) for other in common)),
            key=order_key,
        )
        if not heads:
            shared: list[PlanItem] = []
        elif len(heads) == 1:
            shared = thread(heads[0], done)
        else:
            shared = join(heads, done)

        seen = done | common
        branches = []
        for branch_tip in tips:
            branch_plan = thread(branch_tip, seen)
            if branch_plan:
                branches.append({"from": branch_tip, "plan": branch_plan})
            seen |= ancestors(branch_tip)
        return shared + ([{"merge": branches}] if branches else [])

    return thread(tip, frozenset())
