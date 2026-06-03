import argparse

from common import (
    IMAGE_FIELDS,
    IMAGES_CSV,
    REVIEW_FIELDS,
    REVIEW_QUEUE_CSV,
    now_iso,
    print_json,
    read_csv,
    write_csv,
)


VALID_STATUSES = {"accepted", "rejected", "needs_review"}


def main():
    parser = argparse.ArgumentParser(description="Update curation metadata for one corpus image.")
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--status", required=True, choices=sorted(VALID_STATUSES))
    parser.add_argument("--modality", default="")
    parser.add_argument("--license", default="")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    rows = read_csv(IMAGES_CSV, IMAGE_FIELDS)
    updated = None
    for row in rows:
        if row["image_id"] == args.image_id:
            row["curation_status"] = args.status
            if args.modality:
                row["modality"] = args.modality
            if args.license:
                row["license"] = args.license
            if args.notes:
                row["notes"] = args.notes
            updated = row
            break

    if updated is None:
        print_json({"ok": False, "message": f"Image not found: {args.image_id}"})
        return

    write_csv(IMAGES_CSV, IMAGE_FIELDS, rows)

    if args.status == "needs_review":
        queue = read_csv(REVIEW_QUEUE_CSV, REVIEW_FIELDS)
        if not any(item["image_id"] == args.image_id for item in queue):
            queue.append({"image_id": args.image_id, "reason": args.notes or "Manual review requested.", "created_at": now_iso()})
            write_csv(REVIEW_QUEUE_CSV, REVIEW_FIELDS, queue)

    print_json({"ok": True, "message": f"Updated {args.image_id} to {args.status}.", "image": updated})


if __name__ == "__main__":
    main()
