"""Package the reference adapter and one matching native backend, without caches."""

from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import zipfile


def package(addon: Path, module: Path, output: Path) -> int:
    addon, module, output = addon.resolve(), module.resolve(), output.resolve()
    if not (addon / "__init__.py").is_file():
        raise ValueError(f"Not an add-on source directory: {addon}")
    if not module.is_file() or not module.name.startswith("dsts_formats"):
        raise ValueError("Expected the built dsts_formats native module")
    if module.suffix not in {".pyd", ".so"}:
        raise ValueError("Backend must be a .pyd or .so extension")
    sources = [(path, Path("dsts_formats") / path.relative_to(addon))
               for path in sorted(addon.rglob("*.py"))
               if "__pycache__" not in path.relative_to(addon).parts]
    sources.append((module, Path("dsts_formats") / module.name))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".zip", delete=False) as temp:
        temporary = Path(temp.name)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for source, relative in sources:
                info = zipfile.ZipInfo(relative.as_posix(), (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, source.read_bytes())
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise RuntimeError("Archive verification failed")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return len(sources)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--addon", required=True, type=Path)
    parser.add_argument("--module", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(f"Packaged {package(args.addon, args.module, args.output)} files: {args.output}")


if __name__ == "__main__":
    main()
