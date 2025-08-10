"""
Package initialiser for *scheduler_fapp*.

It makes sure that the package root (where **utils.py** lives) is on
``sys.path`` so that the function entry-point modules can simply use
``import utils`` without failing when Azure Functions loads them.
"""
 
from pathlib import Path
import sys

_pkg_root = Path(__file__).resolve().parent

# Pre-pend (not append) so that our local utils.py wins over any
# similarly-named package that might be installed in the global site-packages.
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))
