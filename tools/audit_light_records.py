"""Validate supported optical edits on explicit local GEOM fixtures."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile


def audit(path, formats):
    raw = path.read_bytes()
    geom = formats.Geom.from_bytes(raw)
    before = [light.raw for light in geom.lights]
    edits = []
    for index, light in enumerate(geom.lights):
        if not light.supports_optical_editing:
            continue
        color, intensity = tuple(light.color_rgb), light.intensity
        light.color_rgb = [max(0.0, c) * .5 for c in color]
        light.intensity = max(0.0, intensity) + .25
        allowed = set(range(8, 12)) | set(range(40, 52))
        if light.native_type == 0:
            light.range = max(0.0, light.range) + 1
            allowed.update(range(12, 16))
        assert all(a == b or offset in allowed for offset, (a, b) in enumerate(zip(before[index], light.raw)))
        edits.append(dict(index=index, native_type=light.native_type, native_slot=light.native_slot,
                          color_before=color, color_after=light.color_rgb,
                          intensity_before=intensity, intensity_after=light.intensity,
                          opaque_bytes_equal=True))
    assert edits, "No supported light in fixture"
    with tempfile.TemporaryDirectory() as folder:
        output = Path(folder) / path.name
        geom.to_file(str(output))
        reopened = formats.Geom.from_bytes(output.read_bytes())
        assert [light.raw for light in reopened.lights] == [light.raw for light in geom.lights]
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
    assert path.read_bytes() == raw
    return dict(path=str(path.resolve()), sha256=hashlib.sha256(raw).hexdigest(),
                light_records=len(before), edits=edits, export_reimport=True,
                exported_sha256=digest, source_unchanged=True, game_test=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("sources", nargs="+", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.module_dir.resolve()))
    formats = importlib.import_module("dsts_formats")
    formats.set_throw_errors(False)
    rows = []
    for path in args.sources:
        try:
            rows.append(audit(path, formats))
        except Exception as exc:
            rows.append(dict(path=str(path.resolve()), error=str(exc)))
    report = dict(schema="dsts-light-edit-validation-v1", passed=sum("error" not in row for row in rows),
                  results=rows, game_test=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}))
    return int(any("error" in row for row in rows))


if __name__ == "__main__":
    sys.exit(main())
