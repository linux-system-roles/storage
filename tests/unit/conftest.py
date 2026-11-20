"""Make the modules in tests/library and tests/module_utils importable."""
import os
import sys

TESTS_BASEDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(1, os.path.join(TESTS_BASEDIR, "..", "library"))
sys.path.insert(1, os.path.join(TESTS_BASEDIR, "..", "module_utils"))
