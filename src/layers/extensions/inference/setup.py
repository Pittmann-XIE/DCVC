# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import os
import glob
import sys
import site
from pathlib import Path
from setuptools import setup
import torch
from torch.utils.cpp_extension import BuildExtension, CUDAExtension


cxx_flags = ["-O3"]
nvcc_flags = ["-O3", "--use_fast_math", "--extra-device-vectorization", "-arch=native"]
if sys.platform == 'win32':
    cxx_flags = ["/O2"]


def get_nvidia_paths(kind):
    paths = []
    for site_dir in site.getsitepackages():
        nvidia_dir = Path(site_dir) / "nvidia"
        if not nvidia_dir.is_dir():
            continue
        paths.extend(str(path) for path in nvidia_dir.glob(f"*/{kind}") if path.is_dir())
    return paths


def get_runtime_library_dirs():
    torch_lib = Path(torch.__file__).resolve().parent / "lib"
    return [str(torch_lib)] + get_nvidia_paths("lib")


setup(
    name='inference_extensions_cuda',
    ext_modules=[
        CUDAExtension(
            name='inference_extensions_cuda',
            sources=glob.glob('*.cpp') + glob.glob('*.cu'),
            include_dirs=get_nvidia_paths("include"),
            library_dirs=get_nvidia_paths("lib"),
            runtime_library_dirs=get_runtime_library_dirs(),
            extra_compile_args={
                "cxx": cxx_flags,
                "nvcc": nvcc_flags,
            },
        ),
    ],
    cmdclass={
        'build_ext': BuildExtension
    }
)
