import argparse

from common import (
    CALIBRATION_CSV,
    CALIBRATION_FIELDS,
    IMAGE_FIELDS,
    IMAGES_CSV,
    now_iso,
    print_json,
    read_csv,
    upsert_rows,
    write_csv,
)


def main():
    parser = argparse.ArgumentParser(description="Store manual scale calibration for a corpus image.")
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--scale-nm", required=True, type=float)
    parser.add_argument("--scale-px", required=True, type=float)
    parser.add_argument("--method", default="manual")
    parser.add_argument("--scale-source", default="manual_scale_bar")
    parser.add_argument("--scale-confidence", default="confirmed")
    parser.add_argument("--magnification", default="")
    parser.add_argument("--instrument", default="")
    parser.add_argument("--sample-prep", default="")
    parser.add_argument("--operator-notes", default="")
    args = parser.parse_args()

    if args.scale_nm <= 0 or args.scale_px <= 0:
        print_json({"ok": False, "message": "scale_nm and scale_px must be positive."})
        return

    nm_per_px = args.scale_nm / args.scale_px
    calibration = {
        "image_id": args.image_id,
        "scale_nm": f"{args.scale_nm:g}",
        "scale_px": f"{args.scale_px:g}",
        "nm_per_px": f"{nm_per_px:.8g}",
        "method": args.method,
        "scale_source": args.scale_source,
        "scale_confidence": args.scale_confidence,
        "magnification": args.magnification,
        "instrument": args.instrument,
        "sample_prep": args.sample_prep,
        "operator_notes": args.operator_notes,
        "updated_at": now_iso(),
    }
    upsert_rows(CALIBRATION_CSV, CALIBRATION_FIELDS, [calibration], "image_id")

    images = read_csv(IMAGES_CSV, IMAGE_FIELDS)
    for image in images:
        if image["image_id"] == args.image_id:
            image["scale_nm"] = calibration["scale_nm"]
            image["scale_px"] = calibration["scale_px"]
            image["nm_per_px"] = calibration["nm_per_px"]
            image["scale_status"] = "confirmed"
            image["updated_at"] = calibration["updated_at"]
            break
    write_csv(IMAGES_CSV, IMAGE_FIELDS, images)

    print_json({"ok": True, "message": f"Calibrated {args.image_id}: {nm_per_px:.8g} nm/px.", "calibration": calibration})


if __name__ == "__main__":
    main()
