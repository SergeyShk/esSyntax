# Installation

Python 3.11 or newer is required. The [anySeg](https://github.com/SergeyShk/anySeg) segmenter and the [esMorph](https://github.com/SergeyShk/esMorph) morphological analyzer are installed together with the package.

``` bash
pip install essyntax
```

## Prebuilt wheels

PyPI hosts wheels for Linux (x86_64 and aarch64, manylinux and musllinux), macOS (Intel and Apple Silicon) and Windows (x64 and arm64). One wheel serves every Python version starting with 3.11, and the free-threaded Python 3.14t and 3.15t have wheels of their own; Rust is not needed to install them. The free-threaded Python 3.13 is not supported: free-threaded builds start with 3.14.

Pre-release versions `X.Y.Z.devN` are published only on TestPyPI:

``` bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ --pre essyntax
```

uv takes a package from the first index that has it, so it needs another order of indexes:

``` bash
uv pip install --extra-index-url https://test.pypi.org/simple/ --index-strategy unsafe-best-match --pre essyntax
```

## Building from source

On other platforms and on free-threaded builds newer than 3.15 pip builds the package from source, which requires [Rust](https://www.rust-lang.org/tools/install) 1.88 or newer:

``` bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
pip install essyntax
```

The development environment is described in [CONTRIBUTING.md](https://github.com/SergeyShk/esSyntax/blob/master/CONTRIBUTING.md).
