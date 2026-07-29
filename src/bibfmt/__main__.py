#!/usr/bin/env python3

# Standard libraries
import argparse
import logging
import sys
from pathlib import Path

# Local libraries
from .formatter import format_bibtex

logger = logging.getLogger(__name__)


def main():
    """
    Main function to execute the formatting.
    """
    argument_parser = argparse.ArgumentParser(
        description="Format a BibTeX file"
    )

    argument_parser.add_argument(
        "file", nargs="?", default="-", help="BibTeX file or - for stdin"
    )

    argument_parser.add_argument(
        "-o",
        "--overwrite",
        action="store_true",
        help="Overwrite the input file",
    )
    argument_parser.add_argument(
        "-i",
        "--indent",
        type=str,
        help="Set indentation",
    )

    args = argument_parser.parse_args()

    indent = "    "
    if args.indent is not None:
        indent = args.indent

    if args.file == "-":
        if args.overwrite:
            logger.error("--overwrite ccanot be used with stdin")

        source = sys.stdin.read()
        sys.stdout.write(format_bibtex(source))
        return

    path = Path(args.file)
    original = path.read_text(encoding="utf-8")
    formatted = format_bibtex(original, indent)

    if args.overwrite:
        args.file.write_text(formatted, encoding="utf-8")
    else:
        sys.stdout.write(formatted)


if __name__ == "__main__":
    main()
