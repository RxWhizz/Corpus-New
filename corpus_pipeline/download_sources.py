import argparse

from common import print_json
from scraper import download_accepted


def main():
    parser = argparse.ArgumentParser(description="Download accepted public corpus sources.")
    parser.parse_args()

    downloaded, errors = download_accepted()
    print_json(
        {
            "ok": not errors,
            "message": f"Downloaded {len(downloaded)} accepted source(s); {len(errors)} error(s).",
            "downloaded": downloaded,
            "errors": errors,
        }
    )


if __name__ == "__main__":
    main()
