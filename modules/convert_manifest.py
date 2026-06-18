#!/usr/bin/env python3

import argparse
import csv
import json
import sys
from pathlib import Path


DEFAULT_CHANNEL_MAP = {
    "DNA": 1,
    "RNA": 2,
    "AGP": 3,
    "ER": 4,
    "Mito": 5,
    "Brightfield": 6,
}

OUTPUT_COLUMNS = [
    "channel",
    "path",
    "source",
    "batch",
    "plate",
    "well",
    "site",
    "col",
    "field_id",
    "plane_id",
    "row",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Convert wide feature-extraction plate manifests into the tall "
            "samplesheet format expected by nf-core/cellpainting."
        )
    )
    parser.add_argument(
        "--manifest-dir",
        required=True,
        help="Directory containing plate manifest TSV files from feature extraction.",
    )
    parser.add_argument(
        "--out",
        default="samplesheet.csv",
        help="Output cellpainting samplesheet CSV path.",
    )
    parser.add_argument(
        "--channel-map",
        default=json.dumps(DEFAULT_CHANNEL_MAP),
        help=(
            "JSON object mapping cellpainting channel names to manifest channel "
            "numbers. Defaults to the feature-extraction channel map."
        ),
    )
    parser.add_argument(
        "--source",
        default=None,
        help=(
            "Fallback source value when manifests do not contain a source column. "
            "Defaults to the first directory under manifest-dir for nested "
            "source/batch manifests, otherwise 'unknown'."
        ),
    )
    return parser.parse_args()


def load_channel_map(raw):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--channel-map must be valid JSON: {exc}") from exc

    if not isinstance(data, dict) or not data:
        raise SystemExit("--channel-map must be a non-empty JSON object")

    channel_map = {}
    for name, number in data.items():
        try:
            channel_number = int(number)
        except (TypeError, ValueError) as exc:
            raise SystemExit(f"Invalid channel number for {name!r}: {number!r}") from exc
        channel_map[str(name)] = channel_number
    return channel_map


def find_manifests(manifest_dir):
    root = Path(manifest_dir)
    if not root.exists():
        raise SystemExit(f"Manifest directory does not exist: {root}")
    if not root.is_dir():
        raise SystemExit(f"Manifest input is not a directory: {root}")

    manifests = sorted(
        path
        for path in root.rglob("*.tsv")
        if not path.name.endswith(".discarded.tsv")
    )
    if not manifests:
        raise SystemExit(f"No manifest TSV files found under {root}")
    return manifests


def require_columns(manifest_path, fieldnames, columns):
    missing = [col for col in columns if col not in fieldnames]
    if missing:
        missing_text = ", ".join(missing)
        raise SystemExit(f"{manifest_path} is missing required columns: {missing_text}")


def value(row, key, default=""):
    result = row.get(key, default)
    return "" if result is None else str(result)


def infer_source(row, manifest_path, manifest_root, fallback_source):
    if "source" in row and value(row, "source"):
        return value(row, "source")
    if fallback_source is not None:
        return fallback_source

    # Feature-extraction manifests are usually manifest_dir/source/batch/plate.tsv
    # when source folders are enabled. If the manifest is only under
    # manifest_dir/batch/file.tsv, there is no source information to infer.
    try:
        parent_parts = manifest_path.parent.relative_to(manifest_root).parts
    except ValueError:
        parent_parts = ()
    if len(parent_parts) >= 2:
        return parent_parts[0]
    return "unknown"


def convert_manifest(manifest_path, manifest_root, channel_map, fallback_source):
    rows = []
    required = ["batch", "plate", "well", "field", "plane", "row", "col"]
    channel_columns = {
        channel_name: f"ch{channel_number}_path"
        for channel_name, channel_number in channel_map.items()
    }

    with manifest_path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise SystemExit(f"{manifest_path} is empty")

        require_columns(manifest_path, reader.fieldnames, required)
        require_columns(manifest_path, reader.fieldnames, channel_columns.values())

        for row in reader:
            source = infer_source(row, manifest_path, manifest_root, fallback_source)
            for channel_name, path_column in channel_columns.items():
                image_path = value(row, path_column)
                if not image_path:
                    continue
                rows.append(
                    {
                        "channel": channel_name,
                        "path": image_path,
                        "source": source,
                        "batch": value(row, "batch"),
                        "plate": value(row, "plate"),
                        "well": value(row, "well"),
                        "site": value(row, "field"),
                        "col": value(row, "col"),
                        "field_id": value(row, "field"),
                        "plane_id": value(row, "plane"),
                        "row": value(row, "row"),
                    }
                )
    return rows


def sort_key(row, channel_order):
    return (
        row["source"],
        row["batch"],
        row["plate"],
        int(row["row"]),
        int(row["col"]),
        int(row["site"]),
        int(row["plane_id"]),
        channel_order[row["channel"]],
    )


def main():
    args = parse_args()
    channel_map = load_channel_map(args.channel_map)
    manifests = find_manifests(args.manifest_dir)
    manifest_root = Path(args.manifest_dir).resolve()
    channel_order = {name: index for index, name in enumerate(channel_map)}

    rows = []
    for manifest in manifests:
        rows.extend(convert_manifest(manifest, manifest_root, channel_map, args.source))

    if not rows:
        raise SystemExit("No image rows were produced from the manifest directory")

    rows.sort(key=lambda row: sort_key(row, channel_order))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"Wrote {len(rows)} rows from {len(manifests)} manifest file(s) to {out_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
