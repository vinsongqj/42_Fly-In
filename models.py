"""
The data models for the simulation are stored here.
"""

from dataclasses import dataclass, field
from enum import Enum


class ZoneType(str, Enum):
    """
    The kind of zone a Zone represents, controlling movement cost and
    whether it can be entered at all.
    """
    NORMAL = "normal"
    BLOCKED = "blocked"
    RESTRICTED = "restricted"
    PRIORITY = "priority"


@dataclass
class Zone:
    """
    A single node in the map: a named location with a position, a
    type, an optional display color, and a capacity limit.

    Attributes:
    - name: Unique identifier used in map files and connection syntax.
    - x: Horizontal coordinate, as declared in the map file.
    - y: Vertical coordinate, as declared in the map file.
    - zone_type: Determines movement cost and passability (see
                 ZoneType).
    - color: Optional color name for terminal/legend display; falls
             back to no color if unset or unrecognized.
    - max_drones: Maximum number of drones allowed to occupy this zone
                  at once (ignored for start/end zones, which have no limit).
    - is_start: True if this is the map's single starting zone.
    - is_end: True if this is the map's single destination zone.
    """
    name: str
    x: int
    y: int
    zone_type: ZoneType = ZoneType.NORMAL
    color: str | None = None
    max_drones: int = 1
    is_start: bool = False
    is_end: bool = False

    def movement_cost(self) -> int:
        """
        Turns required for a drone to enter this zone.

        Returns:
            2 for a `restricted` zone (a drone must commit to a 2-turn
            transit and cannot stop partway); 1 for every other zone type.
            Note: `blocked` zones are excluded from pathfinding entirely,
            so this cost is never actually used for them in practice.
        """
        if self.zone_type == ZoneType.RESTRICTED:
            return 2
        return 1


@dataclass
class Connection:
    """
    An undirected edge linking two zones, with an optional shared
    traffic limit.

    Attributes:
    - zone_a: Name of one endpoint zone.
    - zone_b: Name of the other endpoint zone.
    - max_link_capacity: Maximum number of drones allowed to be
                         traversing this connection simultaneously (default 1).
    """
    zone_a: str
    zone_b: str
    max_link_capacity: int = 1


@dataclass
class Graph:
    """
    The full parsed map: every zone and connection, plus lookup
    structures used by the pathfinder and simulator.

    Attributes:
    - nb_drones: Number of drones to simulate, from the map's
                 `nb_drones:` declaration.
    - zones: All zones in the map, keyed by zone name.
    - connections: All connections in the map, in declaration order.
    - start_zone: Name of the single start zone, or None if not yet set.
    - end_zone: Name of the single end zone, or None if not yet set.
    - adjacency: Maps each zone name to the list of Connections that
                 touch it; built lazily via `build_adjacency()` rather than
                 being kept in sync automatically as zones/connections are
                 added.
    """
    nb_drones: int = 0
    zones: dict[str, Zone] = field(default_factory=dict)
    connections: list[Connection] = field(default_factory=list)
    start_zone: str | None = None
    end_zone: str | None = None
    adjacency: dict[str, list[Connection]] = field(default_factory=dict)

    def build_adjacency(self) -> None:
        """
        (Re)build the zone-name -> incident-connections lookup table.

        Must be called (once, after all zones/connections are added)
        before `neighbors()` will return anything useful. Safe to call
        again if the graph's zones or connections change, since it
        rebuilds the table from scratch each time rather than patching it.
        """
        self.adjacency = {name: [] for name in self.zones}
        for conn in self.connections:
            self.adjacency[conn.zone_a].append(conn)
            self.adjacency[conn.zone_b].append(conn)

    def neighbors(self, zone_name: str) -> list[str]:
        """
        Return the names of every zone directly connected to `zone_name`.

        Args:
            zone_name: The zone to look up neighbors for. Must exist in
                `adjacency` (i.e. `build_adjacency()` must have been
                called since this zone was added) or an empty list is
                returned.

        Returns:
            A list of neighboring zone names, in no particular order.
            Each entry corresponds to one Connection touching `zone_name`.
        """
        result = []
        for conn in self.adjacency.get(zone_name, []):
            other = conn.zone_b if conn.zone_a == zone_name else conn.zone_a
            result.append(other)
        return result
