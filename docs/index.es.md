# esSyntax

**esSyntax** es un analizador sintáctico de dependencias del español: un núcleo en Rust con API para Python. Para cada palabra de una oración el analizador encuentra la palabra de la que depende y la relación entre ambas en la anotación de [Universal Dependencies](https://universaldependencies.org/).

!!! warning "En desarrollo"
    Por ahora el paquete contiene solo la estructura básica; el analizador llegará en las próximas versiones. Las versiones `0.1.0.devN` se publican en TestPyPI.

## Instalación

Se requiere Python 3.11 o superior.

``` bash
pip install essyntax
```

Los paquetes precompilados y la compilación desde el código fuente se describen en la página de [instalación](installation.md).
