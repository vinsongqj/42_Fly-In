"""Command-line entry point for the Fly-in drone routing simulator.

Usage:
    python3 main.py <map_file> [--no-color] [--max-turns N]
"""

import argparse
import sys
from pathlib import Path

from colors import BOLD, colorize
from models import Graph
from parser import ParseError, Parser
from simulator import SimulationError, SimulationResult, Simulator


def _print_legend(graph: Graph, use_color: bool) -> None:
    print(colorize("Zones:", None, use_color))
    for zone in sorted(graph.zones.values(), key=lambda z: z.name):
        role = ""
        if zone.is_start:
            role = " (start)"
        elif zone.is_end:
            role = " (end)"
        label = (
            f"  {zone.name}{role} "
            f"[{zone.zone_type.value}, max_drones={zone.max_drones}]"
        )
        print(colorize(label, zone.color, use_color))
    print()


def _print_turns(
    result: SimulationResult, use_color: bool, graph: Graph
) -> None:
    for turn_number, moves in enumerate(result.turns, start=1):
        prefix = colorize(f"{turn_number:>3}:", None, use_color)
        rendered_moves = []
        for move in moves:
            _, dest = move.split("-", 1)
            zone = graph.zones.get(dest)
            color = zone.color if zone is not None else None
            rendered_moves.append(colorize(move, color, use_color))
        print(f"{prefix} " + " ".join(rendered_moves))


def _print_summary(result: SimulationResult, use_color: bool) -> None:
    header = colorize(
        f"{BOLD}Delivered {result.drones_delivered} drone(s) in "
        f"{result.total_turns} turn(s).",
        None,
        use_color,
    )
    print()
    print(header)


def run_map(
    map_path: Path,
    use_color: bool = True,
    max_turns: int = 2000,
    animate: bool = False,
    animate_delay: float = 0.5,
    animate_clear: bool = True,
    column_spacing: int = 12,
    row_spacing: int = 4,
) -> int:
    """Parse `map_path`, run the simulation, and print results.

    Returns:
        A process exit code (0 on success, 1 on any handled failure).
    """
    try:
        graph = Parser(map_path).parse()
    except ParseError as exc:
        print(f"Parse error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Could not read map file '{map_path}': {exc}", file=sys.stderr)
        return 1

    _print_legend(graph, use_color)

    try:
        simulator = Simulator(graph)
        result = simulator.run(max_turns=max_turns)
    except SimulationError as exc:
        print(f"Simulation error: {exc}", file=sys.stderr)
        return 1

    if animate:
        from visualizer import TerminalVisualizer

        TerminalVisualizer(
            graph,
            result,
            use_color=use_color,
            delay=animate_delay,
            clear=animate_clear,
            column_spacing=column_spacing,
            row_spacing=row_spacing,
        ).run()
        return 0

    _print_turns(result, use_color, graph)
    _print_summary(result, use_color)
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fly-in: multi-drone turn-based routing simulator."
    )
    parser.add_argument("map_file", type=Path, help="Path to a map file.")
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored terminal output.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=2000,
        help="Abort with an error past this many turns (default: 2000).",
    )
    parser.add_argument(
        "--animate",
        action="store_true",
        help="Play a live terminal animation instead of printing turn text.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds between animation frames (default: 0.5).",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help=(
            "With --animate, print each frame sequentially instead of "
            "clearing the screen (useful when redirecting to a file)."
        ),
    )
    parser.add_argument(
        "--column-spacing",
        type=int,
        default=12,
        help=(
            "Characters between tree levels in --animate mode "
            "(default: 12; lower to shrink wide maps, e.g. 5)."
        ),
    )
    parser.add_argument(
        "--row-spacing",
        type=int,
        default=4,
        help=(
            "Rows between siblings in --animate mode "
            "(default: 4; lower to shrink tall maps, e.g. 2)."
        ),
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    return run_map(
        args.map_file,
        use_color=not args.no_color,
        max_turns=args.max_turns,
        animate=args.animate,
        animate_delay=args.delay,
        animate_clear=not args.no_clear,
        column_spacing=args.column_spacing,
        row_spacing=args.row_spacing,
    )


if __name__ == "__main__":
    sys.exit(main())
