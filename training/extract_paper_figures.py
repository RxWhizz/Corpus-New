import argparse
import hashlib
import re
from pathlib import Path


def safe_slug(value, max_length=72):
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", str(value)).strip("_") or "paper"
    slug = re.sub(r"_+", "_", slug)
    if len(slug) <= max_length:
        return slug

    digest = hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:8]
    return f"{slug[: max_length - 9]}_{digest}"


def rgb_or_gray_pixmap(fitz, pix):
    colorspace = getattr(pix, "colorspace", None)
    if colorspace in (fitz.csGRAY, fitz.csRGB) and not pix.alpha:
        return pix
    converted = fitz.Pixmap(fitz.csRGB, pix)
    pix = None
    return converted


def extract_figures(pdf_path, output_dir, min_size=512):
    try:
        import fitz
    except ImportError:
        raise SystemExit("PyMuPDF not installed. Run: pip install pymupdf")

    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = safe_slug(pdf_path.stem)

    doc = fitz.open(str(pdf_path))
    total = 0
    skipped = 0
    errors = []
    for page_index, page in enumerate(doc):
        images = page.get_images(full=True)
        page_count = 0
        for img_index, img in enumerate(images):
            xref = img[0]
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.width < min_size or pix.height < min_size:
                    pix = None
                    skipped += 1
                    continue
                pix = rgb_or_gray_pixmap(fitz, pix)
                out_path = output_dir / f"{page_index + 1:03d}_{img_index + 1:02d}_{xref}.png"
                pix.save(str(out_path))
                pix = None
                page_count += 1
            except Exception as exc:
                errors.append(f"page {page_index + 1}, image {img_index + 1}, xref {xref}: {exc}")
        if page_count:
            print(f"  Page {page_index + 1}: {page_count} image(s)")
        total += page_count

    doc.close()
    print(f"Extracted {total} images >= {min_size}px to {output_dir}")
    if skipped:
        print(f"Skipped {skipped} small image(s)")
    if errors:
        print(f"Skipped {len(errors)} image(s) with extraction errors")
        for error in errors[:10]:
            print(f"  {error}")
        if len(errors) > 10:
            print(f"  ... {len(errors) - 10} more")
    return {"extracted": total, "small_skipped": skipped, "errors": errors}


def main():
    parser = argparse.ArgumentParser(
        description="Extract embedded figures from a paper PDF. Filters by minimum pixel size."
    )
    parser.add_argument("--pdf", required=True, help="Path to the input PDF file.")
    parser.add_argument("--out", required=True, help="Output directory for extracted images.")
    parser.add_argument("--min-size", type=int, default=512, help="Minimum width and height in pixels (default 512).")
    args = parser.parse_args()
    extract_figures(args.pdf, args.out, args.min_size)


if __name__ == "__main__":
    main()
