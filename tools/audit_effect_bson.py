"""Read, edit and re-import explicit local effect BSON fixtures in temp storage."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parents[1] / "addon"))
from effect_bson import EffectDocument


def audit(path):
    raw = path.read_bytes()
    doc = EffectDocument.from_bytes(raw)
    assert doc.to_bytes() == raw
    lifetime = next(field for field in doc.fields if field.path == ("mf",))
    node = doc._get(lifetime.path)
    edited = lifetime.value + 1 if lifetime.value >= 0 else 1
    doc.set_field(lifetime.path, edited)
    result = doc.to_bytes()
    assert result[:node.start + 8] == raw[:node.start + 8] and result[node.end:] == raw[node.end:]
    with tempfile.TemporaryDirectory() as folder:
        output = Path(folder) / path.name
        digest = doc.write(output)
        reopened = EffectDocument.read(output)
        assert reopened.value(("mf",)) == edited and reopened.to_bytes() == result
    assert path.read_bytes() == raw
    return {"path": str(path.resolve()), "source_sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw), "sets": len(doc.sets), "editable_fields": len(doc.fields),
            "exact_preservation": True, "duration_edit": [lifetime.value, edited],
            "unaffected_bytes_equal": True, "source_unchanged": True,
            "exported_sha256": digest, "save_reopen_export": True, "game_test": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path, nargs="+")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for path in args.sources:
        try:
            rows.append(audit(path))
        except Exception as exc:
            rows.append({"path": str(path.resolve()), "error": str(exc)})
    report = {"schema": "dsts-effect-bson-validation-v1", "results": rows,
              "passed": sum("error" not in row for row in rows), "game_test": False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}))
    return int(any("error" in row for row in rows))


if __name__ == "__main__":
    sys.exit(main())
