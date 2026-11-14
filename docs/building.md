# Building and integrating the backend

`dsts_formats` is a native Python extension, not a pure-Python package. Build it
with the development headers and library for the interpreter that loads it.
Check Blender's Python version with `bpy.app.version_string` and `sys.version`
in its console. Blender's version number alone does not identify its Python ABI.

On Windows, use Visual Studio 2022 with the C++ desktop tools and an x64 build.
Install CMake 3.29.3 or later. Use a separate build directory for each Python ABI.

```powershell
$python = 'C:/path/to/python.exe'
& $python -m pip install pybind11
$pybind = & $python -m pybind11 --cmakedir
cmake -S . -B build/cp313 -A x64 "-DPython3_EXECUTABLE=$python" "-Dpybind11_DIR=$pybind"
cmake --build build/cp313 --config Release
```

Copy the resulting `dsts_formats*.pyd` into Time Stranger Importer's `src/`
directory only after validating it against that importer's smoke tests. Keep the
previous build until validation passes. Do not rename a `cp313` binary to imply
support for a different ABI.

Add `-DDSTS_BUILD_REFERENCE_ADDON=ON` to the configure command to also package
the reference add-on in `addon/`. It contains a minimal
GEOM import/export workflow; it is not the complete Time Stranger Importer.

Source assets are external fixtures. Tests should use an explicit extraction
directory or generated samples and report unsupported records, rather than
quietly replacing them with defaults. Do not commit the game's models or dumps.
