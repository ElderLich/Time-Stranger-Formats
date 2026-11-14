"""Audit explicit local SPRK fixtures; never writes source assets or live mods."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

spec = importlib.util.spec_from_file_location("spark", Path(__file__).parents[1] / "addon/spark.py")
spark = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = spark
spec.loader.exec_module(spark)


def audit(path):
    source = path.read_bytes()
    result = {"path": str(path.resolve()), "sha256": hashlib.sha256(source).hexdigest(), "bytes": len(source)}
    doc = spark.SparkDocument.from_bytes(source)
    assert doc.to_bytes() == source
    result["exact_preservation"] = True
    try:
        doc.validate_editable()
    except ValueError as exc:
        result.update(editable=False, rejection=str(exc))
        return result
    node = next(node for node in doc.nodes.values() if node.editable)
    before = node.primary_translation
    doc.set_transform(node.id, "primary", "translation",
                      (before.low[0] + .25, *before.low[1:]),
                      (before.high[0] + .25, *before.high[1:]))
    changed = doc.to_bytes()
    at = doc._node_chunks[node.id].start + 72
    assert changed[:at] == source[:at] and changed[at + 24:] == source[at + 24:]
    with tempfile.TemporaryDirectory() as folder:
        output = Path(folder) / path.name
        digest = doc.write(output)
        reopened = spark.SparkDocument.read(output).validate_editable()
        assert output.read_bytes() == changed and reopened.to_bytes() == changed
        assert reopened.nodes[node.id].primary_translation == doc.nodes[node.id].primary_translation
    assert path.read_bytes() == source
    result.update(editable=True, nodes=len(doc.nodes), edited_node=node.id, changed_range=[at, at + 24],
                  exported_sha256=digest, untouched_bytes_equal=True, source_unchanged=True,
                  save_reopen_export=True, game_test=False)
    return result


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
    report = {"schema": "dsts-spark-validation-v1", "api_version": spark.API_VERSION, "results": rows,
              "preserved": sum(r.get("exact_preservation", False) for r in rows),
              "edited": sum(r.get("editable", False) for r in rows),
              "game_test": False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}))
    return int(any("error" in row for row in rows))


if __name__ == "__main__":
    sys.exit(main())
