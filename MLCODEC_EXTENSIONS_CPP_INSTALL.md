# Installing `MLCodec_extensions_cpp`

This note records the fixes needed to build DCVC's C++ arithmetic-coding
extension on Python 3.12 systems.

## What this extension is

`MLCodec_extensions_cpp` is built from `src/cpp/py_rans/*.cpp`. DCVC uses it for
bitstream writing and arithmetic coding.

## Files that must be present

The `src/cpp` directory should contain a `pyproject.toml` file:

```toml
[build-system]
requires = [
    "setuptools>=61",
    "wheel",
    "pybind11",
]
build-backend = "setuptools.build_meta"
```

This is needed because modern pip builds packages in an isolated environment.
Without this file, pip executes `setup.py` before installing `pybind11`, which
causes:

```text
ModuleNotFoundError: No module named 'pybind11'
```

The Unix compile flags in `src/cpp/setup.py` should not include `-Werror`:

```python
extra_compile_args = ['-std=c++17', '-O3', '-fPIC', '-Wall', '-Wextra']
```

With Python 3.12 and pybind11, headers can emit a harmless
`missing-field-initializers` warning. If `-Werror` is enabled, that warning
stops the build.

## Normal install

From the root of the DCVC repo:

```bash
conda create -n dcvc python=3.12
conda activate dcvc
pip install -r requirements.txt

cd src/cpp
pip install -e .
```

If you do not need editable mode, this also works:

```bash
pip install .
```

## Verify the install

Run:

```bash
python -c "import MLCodec_extensions_cpp; print(MLCodec_extensions_cpp.__name__)"
```

Expected output:

```text
MLCodec_extensions_cpp
```

## Offline or cluster install

If your machine cannot access PyPI during the isolated build, pip may fail while
installing build dependencies, even when `pybind11` is already installed in your
environment. In that case, install the build requirements into the active
environment first:

```bash
conda activate dcvc
pip install setuptools wheel pybind11
```

Then build without isolation:

```bash
cd src/cpp
pip install --no-build-isolation -e .
```

## Troubleshooting

If you see:

```text
ModuleNotFoundError: No module named 'pybind11'
```

make sure `src/cpp/pyproject.toml` exists and lists `pybind11` under
`[build-system].requires`.

If you see:

```text
error: missing initializer for member '_Py_tss_t::_key' [-Werror=missing-field-initializers]
cc1plus: all warnings being treated as errors
```

remove `-Werror` from the Unix `extra_compile_args` in `src/cpp/setup.py`.

If import verification fails after installation, confirm that you are using the
same Python environment for both install and import:

```bash
which python
python -m pip --version
python -c "import sys; print(sys.executable)"
```
