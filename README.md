# BibTeX Formatter

An opinionated formatter for BibTeX files.

## Usage

Install using pip. Run using

```bash
usage: bibfmt [-h] [--sort_global] [-o OUTPUT_FILE]
              [-i INDENT]
              [file]

Format a BibTeX file

positional arguments:
  file                  BibTeX file or - for stdin

options:
  -h, --help            show this help message and
                        exit
  --sort_global         Set to sort the entries
                        globally.
  -o, --output_file OUTPUT_FILE
                        Output file
  -i, --indent INDENT   Set indentation
```
