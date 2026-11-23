"""
Check of the installed package before publishing: parsing of text and the tags of esMorph

Run as `python scripts/smoke.py [version]`; from the `scripts` directory the package is the installed
one, not the sources of the repository.
"""

import sys
import sysconfig
from pathlib import Path

import anyseg
import esmorph

import essyntax

assert "site-packages" in essyntax.__file__, essyntax.__file__
# In Python without the GIL importing the module must not enable the GIL again
if sysconfig.get_config_var("Py_GIL_DISABLED"):
    assert not sys._is_gil_enabled()
if len(sys.argv) > 1:
    assert essyntax.__version__ == sys.argv[1], (essyntax.__version__, sys.argv[1])
# The model of the package and the way from text through the installed anyseg and esmorph
document = essyntax.Parser().parse_text("La niña lee un libro.")
parse = [(word.head, word.deprel) for word in document.words]
expected = [(2, "det"), (3, "nsubj"), (0, "root"), (5, "det"), (3, "obj"), (3, "punct")]
assert parse == expected, parse
if sysconfig.get_config_var("Py_GIL_DISABLED"):
    assert not sys._is_gil_enabled()
# The tags of the installed esMorph are those the model is trained on: data/check.conllu has the
# training tags. The package takes new 0.x versions of esMorph, and the tests of the repository see
# only the one pinned in uv.lock
check = Path(__file__).parents[1] / "data" / "check.conllu"
(document,) = anyseg.read_conllu(check.read_text(encoding="utf-8"))
upos, feats = document.column("upos"), document.column("feats")
tagged = esmorph.Analyzer().annotate(document)
total = len(upos)
upos_diff = sum(a != b for a, b in zip(upos, tagged.column("upos"), strict=True))
feats_diff = sum(a != b for a, b in zip(feats, tagged.column("feats"), strict=True))
assert total > 4000 and max(upos_diff, feats_diff) <= total * 0.005, (
    esmorph.__version__,
    total,
    upos_diff,
    feats_diff,
)
print(f"essyntax {essyntax.__version__}")
