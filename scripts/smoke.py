"""
Check of the installed package before publishing

Run as `python scripts/smoke.py [version]`; from the `scripts` directory the package is the installed
one, not the sources of the repository.
"""

import sys
import sysconfig

import essyntax

assert "site-packages" in essyntax.__file__, essyntax.__file__
# In Python without the GIL importing the module must not enable the GIL again
if sysconfig.get_config_var("Py_GIL_DISABLED"):
    assert not sys._is_gil_enabled()
if len(sys.argv) > 1:
    assert essyntax.__version__ == sys.argv[1], (essyntax.__version__, sys.argv[1])
print(f"essyntax {essyntax.__version__}")
