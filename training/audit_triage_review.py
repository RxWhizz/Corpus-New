import argparse
import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRIAGE_DIR = ROOT / "data" / "interim" / "figures" / "triaged"
DEFAULT_REPORT = ROOT / "reports" / "figure_triage_manual_review.md"
DEFAULT_SUMMARY = DEFAULT_TRIAGE_DIR / "manual_review_summary.csv"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}


PREDICTED_BY_FOLDER = {
    "tem_candidates": "tem",
    "tiles": "tem",
    "graphs": "graph",
    "abstracts_or_schemes": "abstract_or_scheme",
    "mixed": "mixed_figure",
    "needs_review": "needs_review",
}


def rel(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except Exception:
        return str(path)


def manual_label_from_name(name, predicted):
    lowered = name.lower()
    if "graf" in lowered or "graph" in lowered:
        return "graph", "manual_renamed_graph"
    if "abstract" in lowered:
        return "abstract_or_scheme", "manual_renamed_abstract"
    if "separar" in lowered or "separate" in lowered or "split" in lowered:
        return predicted, "manual_needs_split"
    return predicted, "unrenamed_counted_correct"


def rows_from_triage_dir(triage_dir):
    rows = []
    for path in sorted(Path(triage_dir).rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        folder = path.parent.name
        predicted = PREDICTED_BY_FOLDER.get(folder, "unknown")
        manual_label, review_marker = manual_label_from_name(path.name, predicted)
        class_correct = predicted == manual_label
        rows.append(
            {
                "file_path": rel(path),
                "file_name": path.name,
                "folder": folder,
                "predicted_class": predicted,
                "manual_label": manual_label,
                "review_marker": review_marker,
                "class_correct": str(class_correct).lower(),
                "needs_split": str(review_marker == "manual_needs_split").lower(),
            }
        )
    return rows


def percentage(numerator, denominator):
    if not denominator:
        return 0.0
    return 100.0 * numerator / denominator


def summarize(rows):
    total = len(rows)
    markers = Counter(row["review_marker"] for row in rows)
    predicted = Counter(row["predicted_class"] for row in rows)
    manual = Counter(row["manual_label"] for row in rows)
    correct = sum(1 for row in rows if row["class_correct"] == "true")
    split_needed = sum(1 for row in rows if row["needs_split"] == "true")

    tem_outputs = [row for row in rows if row["predicted_class"] == "tem"]
    tem_total = len(tem_outputs)
    tem_false_graph = sum(1 for row in tem_outputs if row["manual_label"] == "graph")
    tem_false_abstract = sum(1 for row in tem_outputs if row["manual_label"] == "abstract_or_scheme")
    tem_needs_split = sum(1 for row in tem_outputs if row["needs_split"] == "true")
    tem_ready = sum(
        1
        for row in tem_outputs
        if row["class_correct"] == "true" and row["needs_split"] == "false"
    )
    tem_class_correct = sum(1 for row in tem_outputs if row["class_correct"] == "true")

    return {
        "total_files": total,
        "class_correct": correct,
        "class_accuracy_percent": percentage(correct, total),
        "split_needed": split_needed,
        "markers": dict(markers),
        "predicted": dict(predicted),
        "manual": dict(manual),
        "tem_outputs": tem_total,
        "tem_false_graph": tem_false_graph,
        "tem_false_abstract": tem_false_abstract,
        "tem_needs_split": tem_needs_split,
        "tem_ready": tem_ready,
        "tem_class_correct": tem_class_correct,
        "tem_class_precision_percent": percentage(tem_class_correct, tem_total),
        "tem_ready_precision_percent": percentage(tem_ready, tem_total),
    }


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "file_path",
        "file_name",
        "folder",
        "predicted_class",
        "manual_label",
        "review_marker",
        "class_correct",
        "needs_split",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_report(path, summary, rows, summary_csv):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Figure Triage Manual Review",
        "",
        "Manual convention:",
        "",
        "- Filenames containing `graf`/`graph` are counted as manually corrected graphs.",
        "- Filenames containing `abstract` are counted as manually corrected abstracts/schemes.",
        "- Filenames containing `separar`/`split` are counted as correct TEM class, but needing panel/figure separation.",
        "- Unrenamed files are counted as correct, per review instruction.",
        "",
        "## Overall",
        "",
        f"- Files reviewed: {summary['total_files']}",
        f"- Class-correct files: {summary['class_correct']} ({summary['class_accuracy_percent']:.1f}%)",
        f"- Files marked as needing separation: {summary['split_needed']}",
        f"- Row-level CSV: `{rel(summary_csv)}`",
        "",
        "## TEM Candidate Output",
        "",
        f"- TEM outputs reviewed: {summary['tem_outputs']}",
        f"- Correct TEM class, including `separar`: {summary['tem_class_correct']} ({summary['tem_class_precision_percent']:.1f}%)",
        f"- Ready TEM without manual split flag: {summary['tem_ready']} ({summary['tem_ready_precision_percent']:.1f}%)",
        f"- False graph in TEM candidates: {summary['tem_false_graph']}",
        f"- False abstract/scheme in TEM candidates: {summary['tem_false_abstract']}",
        f"- TEM candidates needing separation: {summary['tem_needs_split']}",
        "",
        "## Marker Counts",
        "",
    ]
    for name, count in sorted(summary["markers"].items()):
        lines.append(f"- {name}: {count}")
    lines.extend(["", "## Predicted Classes", ""])
    for name, count in sorted(summary["predicted"].items()):
        lines.append(f"- {name}: {count}")
    lines.extend(["", "## Manual Labels", ""])
    for name, count in sorted(summary["manual"].items()):
        lines.append(f"- {name}: {count}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(triage_dir, report_path, summary_csv):
    rows = rows_from_triage_dir(triage_dir)
    summary = summarize(rows)
    write_csv(summary_csv, rows)
    write_report(report_path, summary, rows, summary_csv)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Audit manual filename review markers in the triaged figure folder.")
    parser.add_argument("--triage-dir", default=str(DEFAULT_TRIAGE_DIR))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--summary-csv", default=str(DEFAULT_SUMMARY))
    args = parser.parse_args()
    summary = run(args.triage_dir, args.report, args.summary_csv)
    print(
        json.dumps(
            {
                "ok": True,
                "message": f"Audited {summary['total_files']} triage files with manual rename convention.",
                "report": rel(args.report),
                "summary_csv": rel(args.summary_csv),
                "summary": summary,
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
