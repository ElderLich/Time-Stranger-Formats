#pragma once

#include <string>
#include <pybind11/pybind11.h>

namespace dsts::python {

// Python uses the platform's Unicode-aware filesystem API. Narrow ifstream
// paths on Windows cannot reopen otherwise valid exports such as 光.geom.
inline std::string read_file(const pybind11::str& filename) {
    const auto path=pybind11::module_::import("pathlib").attr("Path")(filename);
    return path.attr("read_bytes")().cast<std::string>();
}

// Call only with the GIL held. Both public backend file writers share this
// publication path after their complete serialization/validation succeeds.
inline void atomic_write(const pybind11::str& filename, const std::string& bytes) {
    namespace py = pybind11;
    // Python's os.replace has replace-existing atomic semantics on Windows as
    // well as POSIX, unlike filesystem::rename on Windows.
    const auto os=py::module_::import("os");
    const auto tempfile=py::module_::import("tempfile");
    const auto path=os.attr("path");
    const auto destination=path.attr("abspath")(filename);
    const auto pair=tempfile.attr("mkstemp")(
        py::arg("dir")=path.attr("dirname")(destination),
        py::arg("prefix")=".dsts-export-",py::arg("suffix")=".tmp");
    py::object descriptor=pair[py::int_(0)];
    const py::object temporary=pair[py::int_(1)];
    py::object file=py::none();
    try {
        file=os.attr("fdopen")(descriptor,"wb");
        descriptor=py::none();
        file.attr("write")(py::bytes(bytes));
        file.attr("flush")();
        os.attr("fsync")(file.attr("fileno")());
        file.attr("close")();
        file=py::none();
        os.attr("replace")(temporary,destination);
    } catch (...) {
        // Best-effort cleanup must preserve the original Python IO exception.
        try {
            if(!file.is_none()) file.attr("close")();
            if(!descriptor.is_none()) os.attr("close")(descriptor);
        } catch (...) { PyErr_Clear(); }
        try { os.attr("unlink")(temporary); }
        catch (...) { PyErr_Clear(); }
        throw;
    }
}

}
