import argparse

from common import print_json
from scraper import extract_figures


def main():
    parser = argparse.ArgumentParser(description="Extract downloadable figure images from accepted sources.")
    parser.add_argument("--max-per-source", type=int, default=20)
    args = parser.parse_args()

    images, errors = extract_figures(args.max_per_source)
    print_json(
        {
            "ok": not errors,
            "message": f"Extracted {len(images)} figure image(s); {len(errors)} error(s).",
            "images": images,
            "errors": errors,
        }
    )


if __name__ == "__main__":
    main()
