# Instalación

Se requiere Python 3.11 o superior. El segmentador [anySeg](https://github.com/SergeyShk/anySeg) y el analizador morfológico [esMorph](https://github.com/SergeyShk/esMorph) se instalan junto con el paquete.

``` bash
pip install essyntax
```

## Paquetes precompilados

PyPI tiene paquetes precompilados para Linux (x86_64 y aarch64, manylinux y musllinux), macOS (Intel y Apple Silicon) y Windows (x64 y arm64). Un mismo paquete sirve para todas las versiones de Python a partir de la 3.11, y Python 3.14t y 3.15t sin GIL tienen los suyos propios; para instalarlos no hace falta Rust. Python 3.13 sin GIL no es compatible: las compilaciones sin GIL empiezan en la 3.14.

Las versiones preliminares `X.Y.Z.devN` se publican solo en TestPyPI:

``` bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ --pre essyntax
```

uv toma un paquete del primer índice que lo tiene, así que necesita otro orden de índices:

``` bash
uv pip install --extra-index-url https://test.pypi.org/simple/ --index-strategy unsafe-best-match --pre essyntax
```

## Compilación desde el código fuente

En otras plataformas y en las compilaciones sin GIL posteriores a la 3.15, pip compila el paquete desde el código fuente, lo que requiere [Rust](https://www.rust-lang.org/tools/install) 1.88 o superior:

``` bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
pip install essyntax
```

El entorno de desarrollo se describe en [CONTRIBUTING.md](https://github.com/SergeyShk/esSyntax/blob/master/CONTRIBUTING.md).

## Rust { #rust }

A partir de la versión 0.1.0 el núcleo del analizador se publica en crates.io como el crate [`essyntax`](https://crates.io/crates/essyntax), y la documentación de la API está en [docs.rs](https://docs.rs/essyntax). El modelo no forma parte del crate: descargue el archivo [`data/es-syntax.bin`](https://github.com/SergeyShk/esSyntax/raw/0.1.0/data/es-syntax.bin) del repositorio en la etiqueta de la versión del crate (la licencia del modelo es CC BY-SA 4.0) y pase su ruta a `Parser::from_path`.

``` bash
cargo add essyntax
```
