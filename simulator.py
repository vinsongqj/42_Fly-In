"""Turn-based drone routing simulator.

Design summary
--------------
Each drone is pre-assigned a path (a sequence of zone names from the start
zone to the end zone), computed once up-front via `pathfinder.k_shortest_paths`
and load-balanced across those paths according to each path's bottleneck
capacity (the tightest `max_drones` / `max_link_capacity` along it). This
gives the "distribution of drones across multiple paths" the subject asks
for, without needing a full multi-commodity-flow solver.

The simulation then advances turn by turn. At each turn:

1. Drones already mid-transit on a restricted (2-turn) connection either
   continue in flight or land, in that priority order.
2. Drones sitting at a zone attempt to advance to the next zone on their
   path, in priority order (drones closest to the end zone go first, since
   freeing zones near the tail of the network tends to unblock the most
   other drones).

Zone occupancy and connection capacity are tracked as live counters rather
than a two-phase conflict-resolution pass: a drone that successfully moves
frees its origin zone immediately (per the subject's rule that "drones
moving out of a zone free up capacity for that same turn"), so
later-processed drones in the same turn can use that freed slot. This is a
deliberate, documented heuristic — resolving truly simultaneous circular
swaps optimally is an NP-hard scheduling problem, and priority-ordered
greedy processing is a standard, explainable approximation for this kind
of turn-based routing.
"""

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from models import Connection, Graph, Zone
from pathfinder import PathfindingError, k_shortest_paths, path_cost


class SimulationError(Exception):
    """
    Raised when a scenario cannot be simulated to completion.
    """


class DroneStatus(str, Enum):
    WAITING = "waiting"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"


@dataclass
class Drone:
    """
    Mutable simulation state for a single drone.
    """

    drone_id: int
    path: list[str]
    remaining_cost_by_position: list[int]
    position: int = 0
    status: DroneStatus = DroneStatus.WAITING
    transit_turns_left: int = 0
    transit_target: str | None = None
    transit_label: str | None = None

    @property
    def current_zone(self) -> str:
        """
        Name of the zone this drone currently occupies (or last left).
        """
        return self.path[self.position]

    @property
    def next_zone(self) -> str | None:
        """
        Name of the next zone on this drone's path, or None at the end.
        """
        if self.position + 1 >= len(self.path):
            return None
        return self.path[self.position + 1]

    @property
    def remaining_cost(self) -> int:
        """
        Turns still needed to reach the end zone from here, ignoring
        any congestion (i.e. the drone's own path cost, not wall-clock
        time). Used to prioritize drones that are cheapest to finish.
        """
        return self.remaining_cost_by_position[self.position]


@dataclass
class SimulationResult:
    """
    Outcome of a completed simulation run.
    """

    turns: list[list[str]]
    total_turns: int
    drones_delivered: int
    paths: dict[int, list[str]]


class Simulator:
    """
    Schedules and simulates a fleet of drones across a `Graph`.
    """

    def __init__(self, graph: Graph, max_paths: int = 4) -> None:
        if graph.start_zone is None or graph.end_zone is None:
            raise SimulationError("Graph is missing a start or end zone")
        if not graph.adjacency:
            graph.build_adjacency()

        self.graph = graph
        self._connections = self._index_connections(graph)
        self.drones: list[Drone] = self._assign_drones(graph, max_paths)
        self.zone_occupancy: dict[str, int] = defaultdict(int)
        self.reserved_zone_slots: dict[str, int] = defaultdict(int)
        self.connection_occupancy: dict[frozenset[str], int] = (
            defaultdict(int)
        )
        self._turn_connection_usage: dict[frozenset[str], int] = (
            defaultdict(int)
        )

    @staticmethod
    def _index_connections(graph: Graph) -> dict[frozenset[str], Connection]:
        """
        Build a direction-agnostic zone-pair -> Connection lookup.
        """
        return {
            frozenset((conn.zone_a, conn.zone_b)): conn
            for conn in graph.connections
        }

    def _connection_between(self, zone_a: str, zone_b: str) -> Connection:
        """
        Look up the `Connection` linking two zones, direction-agnostic.

        Raises:
            SimulationError: if the graph has no such connection -- an
                internal-consistency check, since every path should only
                ever step across edges the graph actually has.
        """
        conn = self._connections.get(frozenset((zone_a, zone_b)))
        if conn is None:
            raise SimulationError(
                f"No connection between '{zone_a}' and '{zone_b}'"
            )
        return conn

    def _path_capacity(self, path: list[str]) -> int:
        """Bottleneck throughput of a path: the tightest zone or link on it."""
        capacity: int | None = None
        for zone_name in path[1:-1]:
            zone = self.graph.zones[zone_name]
            capacity = (
                zone.max_drones
                if capacity is None
                else min(capacity, zone.max_drones)
            )
        for zone_a, zone_b in zip(path, path[1:]):
            conn = self._connection_between(zone_a, zone_b)
            capacity = (
                conn.max_link_capacity
                if capacity is None
                else min(capacity, conn.max_link_capacity)
            )
        return capacity if capacity is not None else 1

    def _select_consistent_paths(
        self, ranked_paths: list[list[str]], max_paths: int
    ) -> list[list[str]]:
        """Pick up to `max_paths` candidates that never cross each other.

        The graph's connections are bidirectional, so Dijkstra is free to
        route one path "backwards" across an edge another path uses
        "forwards" (e.g. to shortcut between two branches). If two chosen
        candidates do that on the same connection, and both endpoint zones
        have tight capacity, the drones assigned to them can end up
        wanting each other's zone at the same time — a genuine head-on
        deadlock, not just a scheduling-order artifact.

        Enforcing that every accepted path traverses each connection in
        only one net direction rules this out entirely, at the cost of
        skipping a few otherwise-cheap "shortcut" candidates.
        """
        accepted: list[list[str]] = []
        used_directions: set[tuple[str, str]] = set()

        for path in ranked_paths:
            directions = list(zip(path, path[1:]))
            reversed_directions = {(b, a) for a, b in directions}
            if reversed_directions & used_directions:
                continue
            accepted.append(path)
            used_directions.update(directions)
            if len(accepted) >= max_paths:
                break

        return accepted or ranked_paths[:1]

    def _assign_drones(self, graph: Graph, max_paths: int) -> list[Drone]:
        """
        Create one `Drone` per `graph.nb_drones`, each pre-assigned to
        one of up to `max_paths` direction-consistent candidate routes,
        greedily load-balanced by current occupancy-to-capacity ratio.

        Raises:
            SimulationError: if no path exists from start to end at all.
        """
        assert graph.start_zone is not None and graph.end_zone is not None

        pool_size = max(1, min(max_paths * 4, graph.nb_drones * 2, 60))
        try:
            ranked_paths = k_shortest_paths(
                graph, graph.start_zone, graph.end_zone, pool_size
            )
        except PathfindingError as exc:
            raise SimulationError(str(exc)) from exc

        candidate_paths = self._select_consistent_paths(
            ranked_paths, max_paths
        )

        capacities = [self._path_capacity(p) for p in candidate_paths]
        costs = [path_cost(graph, p) for p in candidate_paths]
        remaining_costs = [
            self._remaining_cost_table(graph, p) for p in candidate_paths
        ]
        assigned = [0] * len(candidate_paths)

        drones: list[Drone] = []
        for drone_id in range(1, graph.nb_drones + 1):
            best = min(
                range(len(candidate_paths)),
                key=lambda i: (assigned[i] / capacities[i], costs[i]),
            )
            drones.append(
                Drone(
                    drone_id=drone_id,
                    path=candidate_paths[best],
                    remaining_cost_by_position=remaining_costs[best],
                )
            )
            assigned[best] += 1

        self.assigned_paths = {d.drone_id: d.path for d in drones}
        return drones

    @staticmethod
    def _remaining_cost_table(graph: Graph, path: list[str]) -> list[int]:
        """
        Turns needed to reach the end from each index of `path`.
        """
        table = [0] * len(path)
        for i in range(len(path) - 2, -1, -1):
            next_zone = graph.zones[path[i + 1]]
            table[i] = table[i + 1] + next_zone.movement_cost()
        return table

    def run(self, max_turns: int = 2000) -> SimulationResult:
        """
        Advance the simulation until every drone reaches the end zone.

        Raises:
            SimulationError: if a deadlock is detected or `max_turns` is
                exceeded (the scenario is unsolvable as scheduled).
        """
        turns: list[list[str]] = []
        turn = 0

        while any(d.status != DroneStatus.DELIVERED for d in self.drones):
            turn += 1
            if turn > max_turns:
                raise SimulationError(
                    f"Simulation exceeded {max_turns} turns without "
                    "delivering all drones (likely a deadlock or an "
                    "unreachable end zone)."
                )

            self._turn_connection_usage = defaultdict(int)
            self._acted_this_turn: set[int] = set()
            turn_moves: list[str] = []

            self._advance_transits(turn_moves)
            self._advance_waiting(turn_moves)

            if turn_moves:
                turns.append(turn_moves)
            elif any(d.status != DroneStatus.DELIVERED for d in self.drones):
                raise SimulationError(
                    f"Deadlock detected at turn {turn}: no drone can move."
                )

        return SimulationResult(
            turns=turns,
            total_turns=len(turns),
            drones_delivered=sum(
                1 for d in self.drones if d.status == DroneStatus.DELIVERED
            ),
            paths=self.assigned_paths,
        )

    def _priority_order(self, drones: Iterable[Drone]) -> list[Drone]:
        """Order drones cheapest-to-finish first, then by ID.

        Using remaining turn-cost (not raw hop count) matters once
        restricted zones are in play: a drone two hops away but through a
        restricted zone is actually farther, in turns, than a drone three
        hops away through normal zones.
        """
        return sorted(
            drones, key=lambda d: (d.remaining_cost, d.drone_id)
        )

    def _advance_transits(self, turn_moves: list[str]) -> None:
        """
        Tick every in-flight drone's countdown by one turn, completing
        the transit (and freeing its reservation) once it reaches zero.
        """
        in_transit = (
            d for d in self.drones if d.status == DroneStatus.IN_TRANSIT
        )
        for drone in self._priority_order(in_transit):
            drone.transit_turns_left -= 1
            if drone.transit_turns_left <= 0:
                self._complete_transit(drone, turn_moves)
            else:
                turn_moves.append(f"D{drone.drone_id}-{drone.transit_label}")

    def _advance_waiting(self, turn_moves: list[str]) -> None:
        """
        Let every eligible waiting drone attempt one move this turn.

        Excludes drones with no `next_zone` (already at the end) and
        drones that already acted this turn via `_complete_transit`, so
        a drone that just landed can't immediately move again in the
        same turn.
        """
        waiting = (
            d
            for d in self.drones
            if d.status == DroneStatus.WAITING
            and d.next_zone is not None
            and d.drone_id not in self._acted_this_turn
        )
        for drone in self._priority_order(waiting):
            self._attempt_move(drone, turn_moves)

    def _zone_available(self, name: str, zone: Zone) -> bool:
        """
        Whether one more drone could occupy this zone right now.

        Start/end zones have unlimited capacity, per the subject; other
        zones count both physically-present and already-reserved
        (in-flight, about to land) drones against `max_drones`.
        """
        if zone.is_start or zone.is_end:
            return True
        occupied = self.zone_occupancy[name] + self.reserved_zone_slots[name]
        return occupied < zone.max_drones

    def _connection_available(
        self, conn_key: frozenset[str], conn: Connection
    ) -> bool:
        """
        Whether one more drone could use this connection right now,
        counting both multi-turn transits and this-turn single moves
        against `max_link_capacity`.
        """
        used = (
            self.connection_occupancy[conn_key]
            + self._turn_connection_usage[conn_key]
        )
        return used < conn.max_link_capacity

    def _leave_zone(self, name: str) -> None:
        """
        Decrement a zone's live occupancy (no-op for start/end).
        """
        zone = self.graph.zones[name]
        if not (zone.is_start or zone.is_end):
            self.zone_occupancy[name] -= 1

    def _enter_zone_now(self, name: str, zone: Zone) -> None:
        """
        Increment a zone's live occupancy (no-op for start/end).
        """
        if not (zone.is_start or zone.is_end):
            self.zone_occupancy[name] += 1

    def _attempt_move(self, drone: Drone, turn_moves: list[str]) -> None:
        """
        Try to advance `drone` one step along its path this turn.

        If the destination zone or the connecting link is full, the
        drone stays put (no exception, no side effect -- this is the
        mechanism behind "waiting"). Otherwise the drone either arrives
        immediately (normal/priority zones, cost 1) or becomes
        `IN_TRANSIT` for the remaining turns (restricted zones, cost 2+),
        reserving its connection and destination seat for the duration.
        """
        current = drone.current_zone
        target_name = drone.next_zone
        assert target_name is not None
        target_zone = self.graph.zones[target_name]
        conn = self._connection_between(current, target_name)
        conn_key = frozenset((current, target_name))
        cost = target_zone.movement_cost()

        if not self._zone_available(target_name, target_zone):
            return
        if not self._connection_available(conn_key, conn):
            return

        self._leave_zone(current)

        if cost == 1:
            self._turn_connection_usage[conn_key] += 1
            self._enter_zone_now(target_name, target_zone)
            drone.position += 1
            drone.status = (
                DroneStatus.DELIVERED
                if target_zone.is_end
                else DroneStatus.WAITING
            )
            turn_moves.append(f"D{drone.drone_id}-{target_name}")
        else:
            self.connection_occupancy[conn_key] += 1
            self.reserved_zone_slots[target_name] += 1
            drone.status = DroneStatus.IN_TRANSIT
            drone.transit_turns_left = cost - 1
            drone.transit_target = target_name
            drone.transit_label = f"{current}-{target_name}"
            turn_moves.append(f"D{drone.drone_id}-{drone.transit_label}")

    def _complete_transit(self, drone: Drone, turn_moves: list[str]) -> None:
        """
        Land a drone whose restricted-zone transit just finished.

        Releases the connection/seat `_attempt_move` reserved, converts
        the reservation into actual occupancy, and marks the drone
        `_acted_this_turn` so `_advance_waiting` won't move it again
        within the same turn it just landed.
        """
        target_name = drone.transit_target
        assert target_name is not None
        origin_name = drone.current_zone
        conn_key = frozenset((origin_name, target_name))

        self.connection_occupancy[conn_key] -= 1
        self.reserved_zone_slots[target_name] -= 1

        target_zone = self.graph.zones[target_name]
        self._enter_zone_now(target_name, target_zone)

        drone.position += 1
        drone.transit_target = None
        drone.transit_label = None
        drone.status = (
            DroneStatus.DELIVERED
            if target_zone.is_end
            else DroneStatus.WAITING
        )
        self._acted_this_turn.add(drone.drone_id)

        turn_moves.append(f"D{drone.drone_id}-{target_name}")
