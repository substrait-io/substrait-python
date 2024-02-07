// cppimport

#include <pybind11/pybind11.h>
#include <pybind11_abseil/statusor_caster.h>
#include <pybind11_protobuf/native_proto_caster.h>
#include <substrait/common/Io.h>

#define STRINGIFY(x) #x
#define MACRO_STRINGIFY(x) STRINGIFY(x)

int add(int i, int j) {
    return i + j;
}

namespace py = pybind11;

PYBIND11_MODULE(planloader, m) {
    pybind11_protobuf::ImportNativeProtoCasters();

    m.doc() = R"pbdoc(
        Pybind11 example plugin
        -----------------------

        .. currentmodule:: python_example

        .. autosummary::
           :toctree: _generate

           add
           subtract
    )pbdoc";

    m.def("add", &add, R"pbdoc(
        Add two numbers

        Some other explanation about the add function.
    )pbdoc");

    m.def("subtract", [](int i, int j) { return i - j; }, R"pbdoc(
        Subtract two numbers

        Some other explanation about the subtract function.
    )pbdoc");

#ifdef VERSION_INFO
    m.attr("__version__") = MACRO_STRINGIFY(VERSION_INFO);
#else
    m.attr("__version__") = "dev";
#endif
}

/*
<%
setup_pybind11(cfg)
cfg['include_dirs'] = [
    '../../../third_party/pybind11_abseil',
    '../../../third_party/pybind11_protobuf',
    '../../../third_party/substrait-cpp/third_party/abseil-cpp',
    '../../../third_party/substrait-cpp/include',
]
cfg['libraries'] = [
]
%>
*/
