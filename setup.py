from glob import glob
from setuptools import setup
from pybind11.setup_helpers import Pybind11Extension, build_ext

ext_modules = [
    Pybind11Extension(
        "planloader",
        sorted(glob("src/substrait/planloader/*.cpp")),
        include_dirs=[
            'third_party/pybind11_abseil',
            'third_party/pybind11_protobuf',
            'third_party/substrait-cpp/third_party/abseil-cpp',
        ],
    ),
]

setup(cmdclass={"build_ext": build_ext}, ext_modules=ext_modules)
