#!/usr/bin/python3

from pathlib import Path
import sys
import unittest

tests_dir = Path(__file__).absolute().parent
proj_root = tests_dir.parent
src_dir = proj_root / 'src'

sys.path.insert(0, str(src_dir))

loader = unittest.TestLoader()
suite = loader.discover(tests_dir)

runner = unittest.TextTestRunner()
runner.run(suite)
