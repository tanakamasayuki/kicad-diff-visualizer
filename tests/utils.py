import difflib
from pathlib import Path

tests_dir = Path(__file__).absolute().parent
kicad_files_dir = tests_dir / 'kicad_files'

def diff_files(a, b):
    with open(a) as f:
        content_a = f.readlines()
    with open(b) as f:
        content_b = f.readlines()
    d = list(difflib.unified_diff(content_a, content_b))
    if d:
        print('diff (first 10 lines):')
        print(''.join(d[:10]))
        return True
    return False
