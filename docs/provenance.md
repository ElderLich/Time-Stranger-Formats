# Source provenance

The initial commit imports the user-supplied **DSTS_Formats Parser** directory
without source changes: `src/`, `addon/`, `notes/`, `CMakeLists.txt`,
`generate_shader_header.py` and its existing `.gitignore`.

The add-on identifies its author as **Nymic_Razor** and version **0.1.0**.
The original parser is published by
[Named-Blade on the `parser` branch](https://github.com/Named-Blade/dsts-formats/tree/parser). The supplied directory
had no Git history or licence file. This repository does not claim that its
initial commit is an upstream revision, nor assign new licensing terms to it.

`source-manifest.json` records the SHA-256 digest and size of each imported
file. Later changes belong in separate commits with their validation evidence.

## Cleanup at import

Excluded `build/`: CMake cache and project files, compiler intermediates,
generated shader headers, compiled modules and generated archives. These can
be rebuilt and may contain machine-specific paths. No source or format notes
were removed. The original directory remains available as a reference.

`notes/shader_params.bin` is retained because the C++ material parser embeds
it at build time. It is not a disposable compiled artifact.
