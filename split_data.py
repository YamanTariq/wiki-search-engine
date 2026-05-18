import argparse
import bz2
from pathlib import Path


DEFAULT_INPUT = Path("data/simplewiki_meh.bz2")
DEFAULT_OUTPUT = Path("data/simplewiki_10gb.bz2")
DEFAULT_TARGET_SIZE = "10gb"
FOOTER = b"</mediawiki>\n"


SIZE_UNITS = {
    "b": 1,
    "kb": 1000,
    "mb": 1000**2,
    "gb": 1000**3,
    "tb": 1000**4,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
}


def parse_size(value):
    text = value.strip().lower()
    number_part = ""
    unit_part = ""

    for char in text:
        if char.isdigit() or char == ".":
            if unit_part:
                raise argparse.ArgumentTypeError(f"Invalid size: {value}")
            number_part += char
        elif not char.isspace():
            unit_part += char

    if not number_part:
        raise argparse.ArgumentTypeError(f"Invalid size: {value}")

    unit = unit_part or "b"
    if unit not in SIZE_UNITS:
        valid_units = ", ".join(sorted(SIZE_UNITS))
        raise argparse.ArgumentTypeError(
            f"Unknown size unit '{unit}'. Use one of: {valid_units}"
        )

    return int(float(number_part) * SIZE_UNITS[unit])


def is_page_start(line):
    return line.lstrip().startswith(b"<page")


def is_page_end(line):
    return line.lstrip().startswith(b"</page>")


def format_size(size):
    for unit, factor in (("TB", 1000**4), ("GB", 1000**3), ("MB", 1000**2)):
        if size >= factor:
            return f"{size / factor:.2f} {unit}"
    return f"{size} bytes"


def write_chunks(outfile, chunks):
    written = 0
    for chunk in chunks:
        outfile.write(chunk)
        written += len(chunk)
    return written


def split_wikipedia_dump(
    input_file,
    output_file,
    target_uncompressed_bytes,
    progress_every,
    compresslevel,
):
    bytes_written = 0
    pages_written = 0
    found_page = False
    in_page = False
    page_chunks = []
    page_bytes = 0

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with bz2.open(input_file, "rb") as infile, bz2.open(
        output_file, "wb", compresslevel=compresslevel
    ) as outfile:
        for line in infile:
            if not in_page:
                if is_page_start(line):
                    found_page = True
                    in_page = True
                    page_chunks = [line]
                    page_bytes = len(line)
                    continue

                if not found_page:
                    outfile.write(line)
                    bytes_written += len(line)

                continue

            page_chunks.append(line)
            page_bytes += len(line)

            if is_page_end(line):
                bytes_written += write_chunks(outfile, page_chunks)
                pages_written += 1

                if pages_written % progress_every == 0:
                    print(
                        "Pages:",
                        f"{pages_written:,}",
                        "| uncompressed output:",
                        format_size(bytes_written),
                        flush=True,
                    )

                in_page = False
                page_chunks = []
                page_bytes = 0

                if bytes_written >= target_uncompressed_bytes:
                    break

        if not found_page:
            raise RuntimeError("No <page> elements were found. Is this a Wikipedia XML dump?")

        if in_page and page_bytes:
            print("Warning: input ended inside a <page>; the incomplete page was skipped.")

        outfile.write(FOOTER)
        bytes_written += len(FOOTER)

    return pages_written, bytes_written


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Create a smaller Wikipedia .bz2 XML dump by target uncompressed size, "
            "without cutting through page records."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--target-size",
        type=parse_size,
        default=parse_size(DEFAULT_TARGET_SIZE),
        help=(
            "Target uncompressed XML size, for example 10gb, 10gib, 512mb. "
            "Default: 10gb"
        ),
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=50_000,
        help="Print progress after this many complete pages. Default: 50000",
    )
    parser.add_argument(
        "--compresslevel",
        type=int,
        default=1,
        choices=range(1, 10),
        metavar="1-9",
        help="BZ2 compression level for the output. Default: 1, fastest.",
    )
    args = parser.parse_args()

    if args.progress_every <= 0:
        raise SystemExit("--progress-every must be greater than 0")

    print(f"Input: {args.input}")
    print(f"Output: {args.output}")
    print(f"Target uncompressed XML size: {format_size(args.target_size)}")
    print("Splitting on complete <page> records...")

    pages_written, bytes_written = split_wikipedia_dump(
        args.input,
        args.output,
        args.target_size,
        args.progress_every,
        args.compresslevel,
    )

    print("\nDone.")
    print(f"Pages written: {pages_written:,}")
    print(f"Final uncompressed XML size: {format_size(bytes_written)}")
    print(
        "Note: compressed .bz2 size can vary a lot, so use uncompressed XML size "
        "when comparing ingestion workload."
    )


if __name__ == "__main__":
    main()
