from typing import Mapping, Optional


class NotLeafError(ValueError):
    """Endpoint maps this to 409. Only leaf nodes may be prompted."""


def is_leaf(node_id: str, parents: Mapping[str, Optional[str]]) -> bool:
    return node_id in parents and node_id not in parents.values()


def assert_promptable(node_id: str, parents: Mapping[str, Optional[str]]) -> None:
    if node_id not in parents:
        raise KeyError(node_id)
    if not is_leaf(node_id, parents):
        raise NotLeafError(f"node {node_id} has children and cannot be prompted")
