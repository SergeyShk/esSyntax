# Spanish dependency parser (esSyntax)
#
# Copyright (C) 2026
# Author: Sergey Shkarin <kouki.sergey@gmail.com>
# URL: <https://github.com/SergeyShk/esSyntax>

from ._essyntax import Parser, __version__

__description__ = """Fast Spanish dependency parser written in Rust with a Python API.
Requires Python 3.11 or newer"""
__author__ = "Sergey Shkarin"
__author_email__ = "kouki.sergey@gmail.com"

__all__ = ["Parser", "__version__"]
