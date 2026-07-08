"""Small shared ANSI color helpers used by both the plain CLI output
(`main.py`) and the terminal animation (`visualizer.py`).
"""

# Any single-word color name from a map file that doesn't match one of
# these falls back to no color rather than crashing.
#
# The 8 basic names use standard SGR codes (30-37 / 90-97). Everything
# else uses 256-color codes ("38;5;<n>") since plain ANSI has no way to
# represent colors like "gold" or "crimson" distinctly -- these still
# plug into the same `\033[{code}m` format used below, so no other code
# needs to change to support them.
ANSI_COLORS: dict[str, str] = {
    "black": "30",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
    "white": "37",
    "gray": "90",
    "grey": "90",
    "purple": "38;5;129",
    "brown": "38;5;130",
    "orange": "38;5;208",
    "maroon": "38;5;88",
    "gold": "38;5;220",
    "darkred": "38;5;52",
    "violet": "38;5;183",
    "crimson": "38;5;197",
    # "rainbow" has no single-color meaning; bold bright yellow is used
    # as a distinct, eye-catching stand-in for a goal/celebration zone.
    "rainbow": "1;93",
}
RESET = "\033[0m"
BOLD = "\033[1m"
REVERSE = "\033[7m"
CLEAR_SCREEN = "\033[2J\033[H"


def colorize(text: str, color_name: str | None, use_color: bool = True) -> str:
    """Wrap `text` in an ANSI color code for `color_name`, if recognized.

    Falls back to plain `text` when `use_color` is False, `color_name` is
    None, or the color name isn't in `ANSI_COLORS` (never raises on an
    unrecognized color, per the subject's "any single-word string" rule).
    """
    if not use_color or not color_name:
        return text
    code = ANSI_COLORS.get(color_name.lower())
    if code is None:
        return text
    return f"\033[{code}m{text}{RESET}"
