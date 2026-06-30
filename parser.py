from pathlib import Path
from models import ZoneType, Zone, Connection, Graph


class ParseError(Exception):
    def __init__(self, line_number: int, msg: str) -> None:
        self.line_number = line_number
        self.msg = msg
        super().__init__(f"Line {line_number}: {msg}")


class Parser:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.graph = Graph()
        self.seen_connections: set[frozenset[str]] = set()

    def parse(self) -> Graph:
        with open(self.path, encoding="utf-8") as f:
            for line_number, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                self._parse_line(line_number, line)

        if self.graph.nb_drones <= 0:
            raise ParseError(0, "Missing nb_drones declaration")
        if self.graph.start_zone is None:
            raise ParseError(0, "Missing start_hub declaration")
        if self.graph.end_zone is None:
            raise ParseError(0, "Missing end_hub declaration")

        return self.graph

    def _parse_line(self, line_number: int, line: str) -> None:
        if line.startswith("nb_drones:"):
            self._parse_nb_drones(line_number, line)
        elif line.startswith("start_hub:"):
            self._parse_zone_declaration(
                line_number, line, "start_hub:", is_start=True, is_end=False
            )
        elif line.startswith("end_hub:"):
            self._parse_zone_declaration(
                line_number, line, "end_hub:", is_start=False, is_end=True
            )
        elif line.startswith("hub:"):
            self._parse_zone_declaration(
                line_number, line, "hub:", is_start=False, is_end=False
            )
        elif line.startswith("connection:"):
            self._parse_connection_declaration(line_number, line)
        else:
            raise ParseError(line_number, f"Unrecognized line '{line}'")

    def _parse_nb_drones(self, line_number: int, line: str) -> None:
        val = line[len("nb_drones:"):].strip()
        try:
            nb = int(val)
        except ValueError:
            raise ParseError(line_number,
                             f"nb_drones must be an int, got '{val}'")
        if nb <= 0:
            raise ParseError(line_number, "nb_drones must be positive")
        self.graph.nb_drones = nb

    def _parse_zone_declaration(
        self,
        line_number: int,
        line: str,
        prefix: str,
        is_start: bool,
        is_end: bool
    ) -> None:
        rest = line[len(prefix):].strip()
        main_part, meta_part = self.split_brackets(line_number, rest)
        metadata = self.parse_metadata(line_number, meta_part)
        zone = self.parse_zone_line(line_number, main_part,
                                    metadata, is_start, is_end)

        if zone.name in self.graph.zones:
            raise ParseError(line_number, f"Duplicate zone name '{zone.name}'")

        if is_start and self.graph.start_zone is not None:
            raise ParseError(line_number, "Multiple start_hub definitions")
        if is_end and self.graph.end_zone is not None:
            raise ParseError(line_number, "Multiple end_hub definitions")

        self.graph.zones[zone.name] = zone
        if is_start:
            self.graph.start_zone = zone.name
        if is_end:
            self.graph.end_zone = zone.name

    def _parse_connection_declaration(self,
                                      line_number: int,
                                      line: str) -> None:
        rest = line[len("connection:"):].strip()
        conn = self.parse_connection(line_number, rest)
        key = frozenset((conn.zone_a, conn.zone_b))
        if key in self.seen_connections:
            raise ParseError(
                line_number,
                f"Duplicate connection '{conn.zone_a}-{conn.zone_b}'"
            )
        self.seen_connections.add(key)
        self.graph.connections.append(conn)

    def parse_metadata(self, line_number: int, text: str) -> dict[str, str]:
        text = text.strip()
        if not text:
            return {}
        metadata: dict[str, str] = {}
        for token in text.split():
            if "=" not in token:
                raise ParseError(line_number,
                                 f"Invalid metadata token '{token}'")
            key, _, value = token.partition("=")
            if not key or not value:
                raise ParseError(line_number,
                                 f"Invalid metadata token '{token}'")
            if key in metadata:
                raise ParseError(line_number,
                                 f"Duplicate metadata key '{key}'")
            metadata[key] = value
        return metadata

    def split_brackets(self, line_number: int, rest: str) -> tuple[str, str]:
        rest = rest.strip()
        if "[" not in rest and "]" not in rest:
            return rest, ""
        if rest.count("[") != 1 or rest.count("]") != 1:
            raise ParseError(line_number, "Malformed metadata brackets")
        if not rest.endswith("]"):
            raise ParseError(line_number,
                             "Metadata must be closed off with ']'")
        open_idx = rest.index("[")
        main_part = rest[:open_idx].strip()
        meta_part = rest[open_idx + 1:-1]
        return main_part, meta_part

    def parse_zone_line(
        self,
        line_number: int,
        name_x_y: str,
        metadata: dict[str, str],
        is_start: bool,
        is_end: bool,
    ) -> Zone:
        tokens = name_x_y.split()
        if len(tokens) != 3:
            raise ParseError(line_number,
                             f"Expected 'name x y', got '{name_x_y}'")

        name, x_str, y_str = tokens
        if "-" in name:
            raise ParseError(line_number,
                             f"Zone name '{name}' cannot contain '-'")

        try:
            x = int(x_str)
            y = int(y_str)
        except ValueError:
            raise ParseError(
                line_number, f"Coordinates must be int, got '{x_str} {y_str}'"
            )

        zone_type_str = metadata.get("zone", "normal")
        try:
            zone_type = ZoneType(zone_type_str)
        except ValueError:
            raise ParseError(line_number,
                             f"Invalid zone type '{zone_type_str}'")

        max_drones_str = metadata.get("max_drones", "1")
        try:
            max_drones = int(max_drones_str)
        except ValueError:
            raise ParseError(
                line_number,
                f"max_drones must be int, got '{max_drones_str}'"
            )
        if max_drones <= 0:
            raise ParseError(line_number,
                             "max_drones must be a positive integer")

        color = metadata.get("color")

        return Zone(
            name=name,
            x=x,
            y=y,
            zone_type=zone_type,
            color=color,
            max_drones=max_drones,
            is_start=is_start,
            is_end=is_end,
        )

    def parse_connection(self, line_number: int, rest: str) -> Connection:
        main_part, meta_part = self.split_brackets(line_number, rest)
        metadata = self.parse_metadata(line_number, meta_part)

        if "-" not in main_part:
            raise ParseError(line_number,
                             f"Invalid connection syntax '{main_part}'")

        zone_a, _, zone_b = main_part.partition("-")
        zone_a, zone_b = zone_a.strip(), zone_b.strip()

        if zone_a not in self.graph.zones:
            raise ParseError(line_number,
                             f"Unknown zone '{zone_a}' in connection")
        if zone_b not in self.graph.zones:
            raise ParseError(line_number,
                             f"Unknown zone '{zone_b}' in connection")

        cap_str = metadata.get("max_link_capacity", "1")
        try:
            capacity = int(cap_str)
        except ValueError:
            raise ParseError(
                line_number,
                f"max_link_capacity must be an int, got '{cap_str}'"
            )
        if capacity <= 0:
            raise ParseError(line_number,
                             "max_link_capacity must be a positive integer")

        return Connection(zone_a=zone_a,
                          zone_b=zone_b,
                          max_link_capacity=capacity)
