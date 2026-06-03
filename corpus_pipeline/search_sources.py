import argparse

from common import print_json
from scraper import validate_sources


def main():
    parser = argparse.ArgumentParser(description="Validate public corpus sources.")
    parser.add_argument("--sources", default="", help="Newline/comma separated DOI or URL list.")
    args = parser.parse_args()

    rows = validate_sources(args.sources)
    print_json(
        {
            "ok": True,
            "message": f"Validated {len(rows)} source(s).",
            "rows": rows,
            "accepted": sum(1 for row in rows if row.get("decision") == "accepted"),
            "rejected": sum(1 for row in rows if row.get("decision") == "rejected"),
        }
    )


if __name__ == "__main__":
    main()
