import heapq
from models import Graph, ZoneType


class PathfindingError(Exception):
    """Raised when no valid path exists between two zones."""


def path_cost(graph: Graph, path: list[str]) -> int:
    """Return the total movement cost of walking `path` turn-by-turn.

    The cost of entering a zone equals its `movement_cost()`. The start
    zone itself contributes no cost since drones already begin there.
    """
    total = 0
    for zone_name in path[1:]:
        total += graph.zones[zone_name].movement_cost()
    return total


def _dijkstra(
    graph: Graph,
    start: str,
    end: str,
    excluded_edges: set[frozenset[str]] | None = None,
    excluded_nodes: set[str] | None = None,
) -> list[str]:
    """Dijkstra's algorithm restricted to avoid given edges/nodes.

    `excluded_nodes` and `excluded_edges` let Yen's algorithm reuse this
    single implementation to compute "spur paths" while blocking
    previously-found routes.
    """
    excluded_edges = excluded_edges or set()
    excluded_nodes = excluded_nodes or set()

    distances: dict[str, float] = {name: float("inf") for name in graph.zones}
    distances[start] = 0
    previous: dict[str, str | None] = {name: None for name in graph.zones}
    queue: list[tuple[float, str]] = [(0, start)]
    visited: set[str] = set()

    while queue:
        current_cost, current_name = heapq.heappop(queue)

        if current_name in visited:
            continue
        visited.add(current_name)

        if current_name == end:
            break

        for neighbor_name in graph.neighbors(current_name):
            if neighbor_name in excluded_nodes:
                continue
            if frozenset((current_name, neighbor_name)) in excluded_edges:
                continue

            neighbor_zone = graph.zones[neighbor_name]
            if neighbor_zone.zone_type == ZoneType.BLOCKED:
                continue

            candidate_cost = current_cost + neighbor_zone.movement_cost()

            if candidate_cost < distances[neighbor_name]:
                distances[neighbor_name] = candidate_cost
                previous[neighbor_name] = current_name
                heapq.heappush(queue, (candidate_cost, neighbor_name))

    if distances[end] == float("inf"):
        return []

    path: list[str] = []
    current: str | None = end
    while current is not None:
        path.append(current)
        current = previous[current]
    path.reverse()
    return path


def shortest_path(graph: Graph, start: str, end: str) -> list[str]:
    """Return the cheapest zone-to-zone path from `start` to `end`.

    Raises:
        PathfindingError: if `end` is unreachable from `start`.
    """
    path = _dijkstra(graph, start, end)
    if not path:
        raise PathfindingError(f"No path exists from '{start}' to '{end}'")
    return path


def k_shortest_paths(
    graph: Graph, start: str, end: str, k: int
) -> list[list[str]]:
    """Return up to `k` distinct loopless paths from `start` to `end`.

    Uses Yen's algorithm on top of `_dijkstra`. Paths are returned in
    ascending order of total movement cost. Distinct paths let the
    simulator spread drones across several routes instead of funneling
    every drone through a single corridor.
    """
    first = _dijkstra(graph, start, end)
    if not first:
        raise PathfindingError(f"No path exists from '{start}' to '{end}'")

    accepted: list[list[str]] = [first]
    candidates: list[tuple[int, list[str]]] = []
    seen_candidates: set[tuple[str, ...]] = set()

    while len(accepted) < k:
        previous_path = accepted[-1]

        for i in range(len(previous_path) - 1):
            spur_node = previous_path[i]
            root_path = previous_path[: i + 1]

            excluded_edges: set[frozenset[str]] = set()
            for path in accepted:
                if path[: i + 1] == root_path and len(path) > i + 1:
                    excluded_edges.add(frozenset((path[i], path[i + 1])))

            excluded_nodes = set(root_path[:-1])

            spur_path = _dijkstra(
                graph, spur_node, end, excluded_edges, excluded_nodes
            )
            if not spur_path:
                continue

            total_path = root_path[:-1] + spur_path
            key = tuple(total_path)
            if key in seen_candidates or total_path in accepted:
                continue
            seen_candidates.add(key)
            candidates.append((path_cost(graph, total_path), total_path))

        if not candidates:
            break

        candidates.sort(key=lambda item: item[0])
        _, best_path = candidates.pop(0)
        seen_candidates.discard(tuple(best_path))
        accepted.append(best_path)

    return accepted
