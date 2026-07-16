"""
ANSI color helpers used by main.py and visualizer.py.
"""

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
    "rainbow": "1;93",
}
RESET = "\033[0m"
BOLD = "\033[1m"
REVERSE = "\033[7m"
CLEAR_SCREEN = "\033[2J\033[H"


def colorize(text: str, color_name: str | None, use_color: bool = True) -> str:
    """
    Wrap `text` in an ANSI color code for `color_name`, if recognized.

    Falls back to plain `text` when `use_color` is False, `color_name` is
    None, or the color name isn't in `ANSI_COLORS`.
    """
    if not use_color or not color_name:
        return text
    code = ANSI_COLORS.get(color_name.lower())
    if code is None:
        return text
    return f"\033[{code}m{text}{RESET}"
