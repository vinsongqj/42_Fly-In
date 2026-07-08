"""Live terminal animation of a completed simulation.

Layout
------
Zones are arranged as a horizontal tree/diamond lattice: start anchors
the left edge, each zone's column is its BFS-hop distance from start (so
the diagram grows sideways), and within a column zones are stacked using
a tidy-tree row assignment (leaves get sequential rows, each internal
node centers over its children). Branches that fan out and reconverge
naturally read as a diamond, matching the layout style requested.

Edges between zones on the same row are drawn as dashed dots
("· · · ·"); edges that cross rows are drawn as a single dot per row
stepped diagonally (a plain Bresenham line at character-grid
resolution), which is what actually produces a clean diagonal in a
monospace grid.

Drones currently mid-flight on a restricted (multi-turn) connection are
rendered as an inline "D<id>" label at the midpoint of that connection,
so you can see them riding the edge, not just sitting in a zone.
Drones sitting in a zone are shown as a small badge next to that zone's
label instead, to keep the canvas readable.
"""

import re
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field

from colors import RESET, REVERSE, colorize
from models import Graph
from simulator import SimulationResult

_ZONE_TYPE_FALLBACK_COLOR: dict[str, str] = {
    "restricted": "red",
    "priority": "cyan",
    "blocked": "gray",
    "normal": "white",
}
_DOT = "\u00b7"
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_FALLBACK_CLEAR = "\033[2J\033[H"


def _clear_screen() -> None:
    """Clear the terminal via the real `clear` command.

    `clear` looks up the correct escape sequence for the terminal's
    actual terminfo entry, which is more reliable across terminals
    (confirmed necessary for some WSL setups) than assuming a fixed
    ANSI sequence works everywhere. Falls back to that fixed sequence
    only if `clear` itself isn't on PATH.
    """
    try:
        subprocess.run(["clear"], check=False)
    except FileNotFoundError:
        print(_FALLBACK_CLEAR, end="")


def _visible_len(text: str) -> int:
    return len(_ANSI_RE.sub("", text))


def _make_zone_codes(zone_names: list[str]) -> dict[str, str]:
    """Build short, mostly-unique display codes for each zone name.

    E.g. "gate_hell1" and "gate_hell2" become "GH1"/"GH2"; falls back to
    a numeric suffix if two zones still collide after the heuristic.
    """
    used: set[str] = set()
    codes: dict[str, str] = {}
    for name in sorted(zone_names):
        tokens = [t for t in re.split(r"[^A-Za-z0-9]+", name) if t]
        if not tokens:
            tokens = [name]
        initials = "".join(t[0] for t in tokens[:-1]).upper()
        last = tokens[-1]
        last_letters = re.sub(r"[0-9]", "", last)
        last_digits = re.sub(r"[^0-9]", "", last)
        last_part = (last_letters[:1] or "").upper() + last_digits
        code = (initials + last_part) or name[:3].upper()

        candidate = code
        suffix = 0
        while candidate in used:
            suffix += 1
            candidate = f"{code}{suffix}"
        used.add(candidate)
        codes[name] = candidate
    return codes


@dataclass
class _ReplayState:
    """Tracks live drone positions while replaying the recorded turn log."""

    zone_occupants: dict[str, list[int]] = field(default_factory=dict)
    in_flight: dict[int, tuple[str, str]] = field(default_factory=dict)
    _location: dict[int, str] = field(default_factory=dict)

    def apply_move(self, drone_id: int, dest: str, graph: Graph) -> None:
        if dest in graph.zones:
            origin = self._location.get(drone_id)
            if drone_id in self.in_flight:
                del self.in_flight[drone_id]
            elif origin is not None:
                occupants = self.zone_occupants.setdefault(origin, [])
                if drone_id in occupants:
                    occupants.remove(drone_id)
            self.zone_occupants.setdefault(dest, [])
            if drone_id not in self.zone_occupants[dest]:
                self.zone_occupants[dest].append(drone_id)
            self._location[drone_id] = dest
        else:
            origin_zone, target_zone = dest.rsplit("-", 1)
            occupants = self.zone_occupants.setdefault(origin_zone, [])
            if drone_id in occupants:
                occupants.remove(drone_id)
            self.in_flight[drone_id] = (origin_zone, target_zone)


class _Canvas:
    """A plain character grid with collision-aware text placement.

    Every cell always holds exactly one rendered character (colorized
    individually if needed). Earlier versions stored a whole colored
    label string in one cell and left the remaining cells it logically
    spanned as "" placeholders -- but "".join() on a row drops those
    "" cells entirely, silently shrinking the rendered row width by
    (label_length - 1) for every label placed. That drift compounds
    across a row, which is what caused labels/dots to drift into each
    other and eventually overlap completely on wide graphs.
    """

    def __init__(
        self, width: int, height: int, use_color: bool = True
    ) -> None:
        self.width = width
        self.height = height
        self.use_color = use_color
        self._cells: list[list[str]] = [[" "] * width for _ in range(height)]

    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.height and 0 <= col < self.width

    def is_empty(self, row: int, col: int) -> bool:
        return self.in_bounds(row, col) and self._cells[row][col] == " "

    def dot(self, row: int, col: int) -> None:
        if self.is_empty(row, col):
            self._cells[row][col] = colorize(_DOT, "gray", self.use_color)

    def try_place_text(
        self,
        row: int,
        col: int,
        text: str,
        color: str | None = None,
        reverse: bool = False,
    ) -> bool:
        """Place `text` starting at (row, col), one character per cell,
        only if every cell it would occupy is currently empty. Returns
        whether it fit.
        """
        width = len(text)
        if not self.in_bounds(row, col) or col + width > self.width:
            return False
        if not all(self.is_empty(row, col + i) for i in range(width)):
            return False
        for i, ch in enumerate(text):
            self._cells[row][col + i] = self._render_char(ch, color, reverse)
        return True

    def force_place_text(
        self,
        row: int,
        col: int,
        text: str,
        color: str | None = None,
        reverse: bool = False,
    ) -> None:
        """Place `text`, one character per cell, overwriting any dots."""
        width = len(text)
        if not self.in_bounds(row, col):
            return
        col = max(0, min(col, self.width - width))
        for i, ch in enumerate(text):
            if self.in_bounds(row, col + i):
                self._cells[row][col + i] = self._render_char(ch, color,
                                                              reverse)

    def _render_char(self, ch: str, color: str | None, reverse: bool) -> str:
        if reverse and self.use_color:
            return f"{REVERSE}{ch}{RESET}"
        return colorize(ch, color, self.use_color)

    def render(self) -> str:
        return "\n".join("".join(row) for row in self._cells)


class TerminalVisualizer:
    """Plays a completed `SimulationResult` back as a terminal animation."""

    def __init__(
        self,
        graph: Graph,
        result: SimulationResult,
        use_color: bool = True,
        delay: float = 0.5,
        column_spacing: int = 12,
        row_spacing: int = 4,
        max_width: int = 200,
        max_height: int = 60,
        clear: bool = True,
    ) -> None:
        self.graph = graph
        self.result = result
        self.use_color = use_color
        self.delay = delay
        self.column_spacing = column_spacing
        self.row_spacing = row_spacing
        self.codes = _make_zone_codes(list(graph.zones.keys()))
        # Clearing is on by default whenever animation is explicitly
        # requested — don't silently fall back to "print everything"
        # just because stdout.isatty() came back False for some
        # environment-specific reason. --no-clear opts out explicitly
        # (e.g. when redirecting output to a log file).
        self.clear = clear
        self._interactive_stdin = sys.stdin.isatty()

        columns, raw_rows = self._tree_layout()
        self.columns = columns
        self.rows = self._resolve_row_collisions(columns, raw_rows)
        self.width, self.height = self._grid_size(max_width, max_height)

    # -- layout ----------------------------------------------------------

    def _tree_layout(self) -> tuple[dict[str, int], dict[str, float]]:
        """BFS depth -> column; tidy-tree leaf order -> row."""
        assert self.graph.start_zone is not None
        start = self.graph.start_zone

        columns: dict[str, int] = {start: 0}
        children: dict[str, list[str]] = {
            name: [] for name in self.graph.zones
        }
        visited = {start}
        queue: deque[str] = deque([start])

        while queue:
            current = queue.popleft()
            for neighbor in sorted(self.graph.neighbors(current)):
                if neighbor not in visited:
                    visited.add(neighbor)
                    columns[neighbor] = columns[current] + 1
                    children[current].append(neighbor)
                    queue.append(neighbor)

        # Any zone unreachable from start (shouldn't happen on a valid
        # map, but stay robust) becomes its own root at column 0.
        stragglers = [n for n in self.graph.zones if n not in visited]
        for name in stragglers:
            columns[name] = 0

        rows: dict[str, float] = {}
        leaf_counter = [0]

        def assign_rows(node: str) -> float:
            kids = children.get(node, [])
            if not kids:
                rows[node] = float(leaf_counter[0])
                leaf_counter[0] += 1
                return rows[node]
            child_rows = [assign_rows(k) for k in kids]
            rows[node] = sum(child_rows) / len(child_rows)
            return rows[node]

        assign_rows(start)
        for name in stragglers:
            rows[name] = float(leaf_counter[0])
            leaf_counter[0] += 1

        return columns, rows

    @staticmethod
    def _resolve_row_collisions(
        columns: dict[str, int], rows: dict[str, float]
    ) -> dict[str, int]:
        """Round tidy-tree rows to integers, nudging apart any two zones
        that land on the same (column, row) after rounding.
        """
        by_column: dict[int, list[str]] = {}
        for name, col in columns.items():
            by_column.setdefault(col, []).append(name)

        resolved: dict[str, int] = {}
        for names in by_column.values():
            used_rows: set[int] = set()
            for name in sorted(names, key=lambda n: rows[n]):
                target = round(rows[name])
                while target in used_rows:
                    target += 1
                used_rows.add(target)
                resolved[name] = target
        return resolved

    def _grid_size(
        self, max_width: int, max_height: int
    ) -> tuple[int, int]:
        max_col = max(self.columns.values())
        max_row = max(self.rows.values()) if self.rows else 0
        required_width = (max_col + 1) * self.column_spacing + 6
        required_height = int((max_row + 2) * self.row_spacing)

        if required_width > max_width or required_height > max_height:
            print(
                f"Note: this map needs a {required_width}x{required_height} "
                f"character canvas, larger than the default "
                f"{max_width}x{max_height}. Widening the canvas instead of "
                "clipping it (clipping caused overlapping zones). Widen "
                "your terminal, or lower column_spacing/row_spacing, if "
                "the layout doesn't fit on screen.",
                file=sys.stderr,
            )

        return max(required_width, 20), max(required_height, 8)

    def _pos(self, name: str) -> tuple[int, int]:
        """Character-grid (row, col) anchor for a zone's label."""
        row = 1 + self.rows[name] * self.row_spacing
        col = 2 + self.columns[name] * self.column_spacing
        return row, col

    def _center(self, name: str) -> tuple[int, int]:
        row, col = self._pos(name)
        return row, col + len(self.codes[name]) // 2

    # -- edge drawing --------------------------------------------------

    def _draw_edge(self, canvas: _Canvas, zone_a: str, zone_b: str) -> None:
        r0, c0 = self._center(zone_a)
        r1, c1 = self._center(zone_b)
        left_r, left_c = (r0, c0) if c0 <= c1 else (r1, c1)
        right_r, right_c = (r1, c1) if c0 <= c1 else (r0, c0)

        if left_r == right_r:
            # Same row: a dashed line of dots. If the gap is too tight
            # for a stepped dashed line, still place one dot so a real
            # connection is never rendered as if it didn't exist.
            cols = list(range(left_c + 2, right_c - 1, 2))
            if not cols and right_c - left_c > 2:
                cols = [(left_c + right_c) // 2]
            for col in cols:
                canvas.dot(left_r, col)
            return

        # Different rows: orthogonal elbow routing (horizontal, then
        # vertical, then horizontal), turning at the midpoint column.
        # Free-form diagonals get tangled fast on a dense graph; a
        # consistent horizontal/vertical grid reads far more cleanly,
        # the same reason tree/org-chart diagrams use elbow connectors.
        turn_col = (left_c + right_c) // 2
        turn_col = max(left_c + 2, min(turn_col, right_c - 2))

        for col in range(left_c + 2, turn_col, 2):
            canvas.dot(left_r, col)
        if turn_col - left_c > 2 and not range(left_c + 2, turn_col, 2):
            canvas.dot(left_r, (left_c + turn_col) // 2)

        row_step = 1 if right_r > left_r else -1
        for row in range(left_r, right_r + row_step, row_step):
            canvas.dot(row, turn_col)

        for col in range(turn_col + 2, right_c - 1, 2):
            canvas.dot(right_r, col)
        if right_c - turn_col > 2 and not range(turn_col + 2, right_c - 1, 2):
            canvas.dot(right_r, (turn_col + right_c) // 2)

    # -- rendering ---------------------------------------------------------

    def _zone_color(self, zone_name: str) -> str | None:
        zone = self.graph.zones[zone_name]
        return zone.color or _ZONE_TYPE_FALLBACK_COLOR.get(
            zone.zone_type.value
        )

    def _render_grid(self, state: _ReplayState) -> str:
        canvas = _Canvas(self.width, self.height, self.use_color)

        for conn in self.graph.connections:
            self._draw_edge(canvas, conn.zone_a, conn.zone_b)

        for name in self.graph.zones:
            row, col = self._pos(name)
            code = self.codes[name]
            occupants = state.zone_occupants.get(name)
            if occupants:
                badge = "".join(f"D{d}" for d in occupants[:1])
                if len(occupants) > 1:
                    badge += f"+{len(occupants) - 1}"
                if self.use_color:
                    canvas.force_place_text(row, col, code, reverse=True)
                    canvas.force_place_text(row, col + len(code), f"({badge})")
                else:
                    canvas.force_place_text(row, col, f"[{code}]({badge})")
            else:
                canvas.force_place_text(
                    row, col, code, color=self._zone_color(name)
                )

        overflow: list[str] = []
        for drone_id, (origin, target) in state.in_flight.items():
            r0, c0 = self._center(origin)
            r1, c1 = self._center(target)
            mid_row = (r0 + r1) // 2
            mid_col = (c0 + c1) // 2
            text = f"D{drone_id}"
            if not canvas.try_place_text(mid_row, mid_col, text,
                                         color="yellow"):
                overflow.append(f"D{drone_id} ({origin}\u2192{target})")

        grid_text = canvas.render()
        if overflow:
            grid_text += "\n\nAlso in flight: " + ", ".join(overflow)
        return grid_text

    def _render_legend(self) -> str:
        lines = ["Zone legend (code=name[type]):"]
        entries = []
        for name in sorted(self.codes):
            zone = self.graph.zones[name]
            role = (
                " start" if zone.is_start else " end" if zone.is_end else ""
            )
            entries.append(
                f"{self.codes[name]}={name}[{zone.zone_type.value}{role}]"
            )
        chunk = 4
        for i in range(0, len(entries), chunk):
            lines.append("  " + "  ".join(entries[i: i + chunk]))
        return "\n".join(lines)

    def _render_footer(
        self, turn_number: int, total_turns: int, moves: list[str]
    ) -> str:
        header = colorize(
            f"Turn {turn_number}/{total_turns}", None, self.use_color
        )
        return f"{header}\n" + " ".join(moves)

    # -- playback ------------------------------------------------------

    def run(self) -> None:
        """Print the legend once, then animate every recorded turn."""
        print(self._render_legend())
        print()
        if self._interactive_stdin:
            input("Press Enter to start the animation...")

        state = _ReplayState()
        total = len(self.result.turns)
        for turn_number, moves in enumerate(self.result.turns, start=1):
            for move in moves:
                drone_id_str, dest = move.split("-", 1)
                state.apply_move(int(drone_id_str[1:]), dest, self.graph)

            frame = (
                self._render_grid(state)
                + "\n\n"
                + self._render_footer(turn_number, total, moves)
            )
            if self.clear:
                _clear_screen()
                print(frame, flush=True)
                time.sleep(self.delay)
            else:
                print(frame)
                print("-" * min(self.width, 80))

        summary = colorize(
            f"Delivered {self.result.drones_delivered} drone(s) in "
            f"{self.result.total_turns} turn(s).",
            None,
            self.use_color,
        )
        print()
        print(summary)
