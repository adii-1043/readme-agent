"""Small helpers for consistent console output formatting."""

BANNER_WIDTH = 76


def print_section(title: str, body: str) -> None:
    bar = "=" * BANNER_WIDTH
    print(f"\n{bar}\n{title.upper().center(BANNER_WIDTH)}\n{bar}\n{body.rstrip()}\n{bar}\n")

