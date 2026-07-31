#!/usr/bin/env python3

# Standard libraries
import argparse
import logging
import sys
from pathlib import Path

# Local libraries
from .formatter import parse_bib

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
        "--sort_global",
        action="store_false",
        help="Set to sort the entries globally.",
    )
    argument_parser.add_argument(
        "-o",
        "--output_file",
        type=str,
        help="Output file",
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

    # If - is given write to stdout
    if args.file == "-":
        if args.output_file:
            logger.error("--output_file cannot be used with stdin")

        source = sys.stdin.read()
        bib = parse_bib(source, indent)

        if args.sort_global:
            bib.sort_global()

        sys.stdout.write(bib.get_text())
        return

    input_path = Path(args.file)
    original = input_path.read_text(encoding="utf-8")
    bib = parse_bib(original, indent)

    if args.sort_global:
        bib.sort_global()

    formatted = bib.get_text()

    # If output file is given write to it
    if args.output_file:
        output_path = Path(args.output_file)
        output_path.write_text(formatted, encoding="utf-8")
    else:
        # Otherwise write to the given file
        sys.stdout.write(formatted)


if __name__ == "__main__":
    main()
