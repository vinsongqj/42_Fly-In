from pathlib import Path
from models import ZoneType, Zone, Connection, Graph


class ParseError(Exception):
    """
    The default error raised when encountering a parsing error.
    """
    def __init__(self, line_number: int, msg: str) -> None:
        self.line_number = line_number
        self.msg = msg
        super().__init__(f"Line {line_number}: {msg}")


class Parser:
    """
    The class that handles the parsing of the map file.
    """
    def __init__(self, path: Path) -> None:
        """
        Initializes the parser.
        """
        self.path = path
        self.graph = Graph()
        self.seen_connections: set[frozenset[str]] = set()

    def parse(self) -> Graph:
        """
        Parse `self.path` into a fully-populated `Graph`.

        Reads the whole file, verifies the first non-comment line is
        `nb_drones:` (a hard requirement, not just a per-line check,
        since it can only be confirmed by looking at the file as a
        whole), dispatches every other line by its prefix, then runs
        whole-file checks that also can't be done line-by-line (exactly
        one start/end zone declared, `nb_drones` actually set).

        Raises:
            ParseError: on any malformed or missing required content.
        """

        with open(self.path, encoding="utf-8") as f:
            lines = f.readlines()

        first_line = None
        first_line_number = None
        for line_number, raw_line in enumerate(lines, start=1):
            stripped = raw_line.strip()
            if stripped and not stripped.startswith("#"):
                first_line = stripped
                first_line_number = line_number
                break

        if first_line is None or not first_line.startswith("nb_drones:"):
            raise ParseError(
                first_line_number or 1,
                "First non-comment line must be 'nb_drones: int(>0)'"
            )

        for line_number, raw_line in enumerate(lines, start=1):
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

        self.graph.build_adjacency()
        return self.graph

    def _parse_line(self, line_number: int, line: str) -> None:
        """
        Dispatch one already-stripped, non-blank, non-comment line to
        the parsing function matching its prefix.

        Raises:
            ParseError: if the line matches none of the known prefixes.
        """
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
        """
        Parse an `nb_drones: <int>` line and store it on the graph.

        Raises:
            ParseError: if the value isn't an integer, or isn't positive.
        """
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
        """
        Parse a `hub:`/`start_hub:`/`end_hub:` line into a `Zone` and
        register it on the graph.

        All three prefixes share the exact same `name x y [metadata]`
        shape, so `_parse_line` routes them all here with `is_start`/
        `is_end` set accordingly, instead of duplicating this logic
        three times.

        Raises:
            ParseError: on a duplicate zone name, or a second
                `start_hub`/`end_hub` declaration.
        """
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
        """
        Parse a `connection:` line into a `Connection` and register it.

        Raises:
            ParseError: if this exact connection (in either direction)
                was already declared earlier in the file.
        """
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
        """
        Parse a `key=value key2=value2 ...` metadata string into a dict.

        `text` is the raw content between `[` and `]` (or an empty
        string if a line had no metadata block at all) -- shared by both
        zone and connection lines, since they use the same syntax.
        Values are returned as plain strings; each caller is responsible
        for converting to the type it actually expects (e.g. `int` for
        `max_drones`).

        Raises:
            ParseError: on a malformed token (missing `=`, empty key or
                value), or a key repeated within the same bracket.
        """
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
        """
        Split off an optional trailing `[...]` metadata block.

        E.g. `"roof1 3 4 [zone=restricted color=red]"` becomes
        `("roof1 3 4", "zone=restricted color=red")`. If there's no
        bracket at all, returns `(rest, "")` unchanged.

        Raises:
            ParseError: if brackets are present but malformed (not
                exactly one pair, or not at the end of the line).
        """
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
        """
        Build a `Zone` from its `"name x y"` part plus parsed metadata.

        Applies the documented defaults for any metadata key that's
        absent (`zone=normal`, `max_drones=1`, no color).

        Raises:
            ParseError: on a malformed `name x y` shape, a name
                containing `-`, non-integer coordinates, an invalid
                `zone` type, or a non-positive `max_drones`.
        """
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
        """
        Build a `Connection` from a `"zoneA-zoneB [metadata]"` string.

        Requires both `zoneA` and `zoneB` to already be registered on
        the graph -- since zones are parsed top-to-bottom before
        connections are validated, this naturally enforces the
        "connections may only reference previously-defined zones" rule.

        Raises:
            ParseError: on malformed `zoneA-zoneB` syntax, a reference to
                an unknown zone, or a non-positive `max_link_capacity`.
        """
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
