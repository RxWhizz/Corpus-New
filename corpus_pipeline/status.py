import argparse

from common import (
    CALIBRATION_CSV,
    CALIBRATION_FIELDS,
    IMAGE_FIELDS,
    IMAGES_CSV,
    REVIEW_FIELDS,
    REVIEW_QUEUE_CSV,
    SOURCE_FIELDS,
    SOURCES_CSV,
    print_json,
    read_csv,
)


def main():
    parser = argparse.ArgumentParser(description="Read corpus pipeline state for the GUI.")
    parser.parse_args()
    sources = read_csv(SOURCES_CSV, SOURCE_FIELDS)
    images = read_csv(IMAGES_CSV, IMAGE_FIELDS)
    calibrations = read_csv(CALIBRATION_CSV, CALIBRATION_FIELDS)
    review_queue = read_csv(REVIEW_QUEUE_CSV, REVIEW_FIELDS)

    print_json(
        {
            "ok": True,
            "message": "Corpus state loaded.",
            "sources": sources,
            "images": images,
            "calibrations": calibrations,
            "reviewQueue": review_queue,
            "summary": {
                "sources": len(sources),
                "acceptedSources": sum(1 for row in sources if row["decision"] == "accepted"),
                "images": len(images),
                "acceptedImages": sum(1 for row in images if row["curation_status"] == "accepted"),
                "rejectedImages": sum(1 for row in images if row["curation_status"] == "rejected"),
                "needsReview": sum(1 for row in images if row["curation_status"] == "needs_review"),
                "calibrated": sum(1 for row in images if row.get("nm_per_px")),
                "publicationReadySources": sum(1 for row in sources if row.get("license_status") == "accepted"),
                "licenseBlockedSources": sum(1 for row in sources if row.get("license_status") == "rejected_for_public_corpus"),
                "imagesMissingCaption": sum(1 for row in images if not (row.get("caption") or row.get("notes"))),
                "imagesMissingScale": sum(1 for row in images if not row.get("nm_per_px")),
                "imagesMissingChecksum": sum(1 for row in images if not row.get("file_sha256")),
                "metadataReadyImages": sum(1 for row in images if row.get("metadata_status") == "ready"),
            },
        }
    )


if __name__ == "__main__":
    main()
