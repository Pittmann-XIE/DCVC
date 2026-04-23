# Installing `inference_extensions_cuda`

This note documents the working install path for the custom CUDA inference
extension in `src/layers/extensions/inference`.

The extension depends on PyTorch at build time, compiles `.cu` sources with
`nvcc`, and links against PyTorch and NVIDIA CUDA libraries. For that reason it
should be built inside the same Python environment that will run inference.

## Tested Setup

The fix was verified with:

- Python 3.12
- PyTorch `2.11.0+cu126`
- CUDA compiler `nvcc` 12.6
- Conda GCC/G++ 11.2

Other CUDA 12.x and PyTorch builds may work, but keep the CUDA compiler version
close to the CUDA version used by your PyTorch wheel.

## Prerequisites

Create and activate your environment, then install PyTorch and the Python
requirements:

```bash
conda create -n python312t python=3.12
conda activate python312t

pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
pip install -r requirements.txt
```

Install a real CUDA compiler into the same conda environment:

```bash
conda install -c nvidia cuda-nvcc=12.6
```

This is important. Runtime CUDA packages can be enough to import PyTorch, but
they are not enough to compile this extension. PyTorch's CUDA extension builder
needs an `nvcc` executable.

Check that the environment has `nvcc`:

```bash
which nvcc
nvcc --version
```

The `which nvcc` output should point inside the active conda environment, for
example:

```text
$CONDA_PREFIX/bin/nvcc
```

## Build The Extension

From the repository root:

```bash
conda activate python312t

cd src/cpp
pip install .

cd ../layers/extensions/inference
CUDA_HOME="$CONDA_PREFIX" \
CC="$CONDA_PREFIX/bin/x86_64-conda-linux-gnu-gcc" \
CXX="$CONDA_PREFIX/bin/x86_64-conda-linux-gnu-g++" \
pip install --no-build-isolation -e .
```

Use `--no-build-isolation` for this extension. Without it, pip creates a
temporary build environment that does not see the already-installed PyTorch
package, and the build can fail with:

```text
ModuleNotFoundError: No module named 'torch'
```

Setting `CUDA_HOME="$CONDA_PREFIX"` makes PyTorch use the conda CUDA toolkit.
Setting `CC` and `CXX` makes the build use conda's GCC/G++ instead of an older
system compiler.

## Verify The Install

Run:

```bash
python -c "import inference_extensions_cuda; print('ok', inference_extensions_cuda.__name__)"
```

Expected output:

```text
ok inference_extensions_cuda
```

## What Was Fixed In This Repo

The following corrections were made so the extension builds reliably in modern
Python/PyTorch/CUDA environments:

- Added `src/layers/extensions/inference/pyproject.toml` with a minimal
  setuptools build backend.
- Updated `src/layers/extensions/inference/setup.py` to add NVIDIA package
  include/library directories from `site-packages/nvidia/*`.
- Added runtime library directories for PyTorch's `torch/lib` and NVIDIA CUDA
  wheel libraries, so importing the extension does not require a manual
  `LD_LIBRARY_PATH`.
- Constrained broad vector helper templates in `common.h` so they do not collide
  with PyTorch/pybind11 internals.
- Converted `c10::Half` explicitly to CUDA `__half` before calling CUDA half
  intrinsics.
- Replaced fragile half `hlog` / `__hfma` calls with float-backed CUDA math
  conversions compatible with CUDA 12.6 headers.

## Common Errors

### `ModuleNotFoundError: No module named 'torch'`

Build isolation hid the PyTorch install from the extension build.

Fix:

```bash
pip install --no-build-isolation -e .
```

### `CUDA_HOME environment variable is not set`

PyTorch could not find a CUDA toolkit.

Fix:

```bash
CUDA_HOME="$CONDA_PREFIX" pip install --no-build-isolation -e .
```

Also confirm `nvcc` exists:

```bash
which nvcc
```

### `You're trying to build PyTorch with a too old version of GCC`

The build is using an old system compiler.

Fix:

```bash
CC="$CONDA_PREFIX/bin/x86_64-conda-linux-gnu-gcc" \
CXX="$CONDA_PREFIX/bin/x86_64-conda-linux-gnu-g++" \
pip install --no-build-isolation -e .
```

If those compiler paths do not exist, install conda's CUDA compiler package:

```bash
conda install -c nvidia cuda-nvcc=12.6
```

### `fatal error: cusparse.h: No such file or directory`

The CUDA headers are installed through NVIDIA Python wheels, but the extension
build did not include their paths. This repo's updated `setup.py` adds those
paths automatically. Pull the latest repo changes and rebuild.

### `ImportError: libc10.so: cannot open shared object file`

The extension was built without PyTorch runtime library paths.

This repo's updated `setup.py` adds PyTorch's `torch/lib` as a runtime library
directory. Rebuild the extension:

```bash
pip install --no-build-isolation -e .
```

As a temporary workaround, add PyTorch's library directory to `LD_LIBRARY_PATH`:

```bash
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib/python3.12/site-packages/torch/lib:$LD_LIBRARY_PATH"
```

