from dataclasses import dataclass, field
from enum import Enum


class ZoneType(str, Enum):
    NORMAL = "normal"
    BLOCKED = "blocked"
    RESTRICTED = "restricted"
    PRIORITY = "priority"


@dataclass
class Zone:
    name: str
    x: int
    y: int
    zone_type: ZoneType = ZoneType.NORMAL
    color: str | None = None
    max_drones: int = 1
    is_start: bool = False
    is_end: bool = False

    def movement_cost(self) -> int:
        if self.zone_type == ZoneType.RESTRICTED:
            return 2
        return 1


@dataclass
class Connection:
    zone_a: str
    zone_b: str
    max_link_capacity: int = 1


@dataclass
class Graph:
    nb_drones: int = 0
    zones: dict[str, Zone] = field(default_factory=dict)
    connections: list[Connection] = field(default_factory=list)
    start_zone: str | None = None
    end_zone: str | None = None
    adjacency: dict[str, list[Connection]] = field(default_factory=dict)

    def build_adjacency(self) -> None:
        self.adjacency = {name: [] for name in self.zones}
        for conn in self.connections:
            self.adjacency[conn.zone_a].append(conn)
            self.adjacency[conn.zone_b].append(conn)

    def neighbors(self, zone_name: str) -> list[str]:
        result = []
        for conn in self.adjacency.get(zone_name, []):
            other = conn.zone_b if conn.zone_a == zone_name else conn.zone_a
            result.append(other)
        return result
