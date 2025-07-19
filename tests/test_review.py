import difflib
import filecmp
from pathlib import Path
import shutil
import tempfile
import unittest

import git

import kidivis.review

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

class TestGitOperations(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix='kidivis'))
        print(f'temporary directory: {self.tmpdir}')
        (self.tmpdir / 'extract').mkdir()

        kicad_files = ['sample.kicad_' + kind for kind in ['pro', 'sch', 'pcb']]

        self.git_repo = git.Repo.init(self.tmpdir / 'repo')
        repo_root = self.git_repo.working_tree_dir

        for f in kicad_files:
            shutil.copy(kicad_files_dir / 'sample1' / f, repo_root)
        self.git_repo.index.add(kicad_files)
        self.initial_commit = self.git_repo.index.commit('initial commit')

        for f in kicad_files:
            shutil.copy(kicad_files_dir / 'sample2' / f, repo_root)
        self.git_repo.index.add(kicad_files)
        self.second_commit = self.git_repo.index.commit('second commit')

        for f in kicad_files:
            shutil.copy(kicad_files_dir / 'sample3' / f, repo_root)
        # コミットしない。変更がワーキングツリーだけにある状態とする。

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_extract_file_from_initial_commit(self):
        # initial commit のファイル抽出
        output_path = self.tmpdir / 'extract/initial_commit.kicad_pcb'
        kidivis.review.extract_file(self.git_repo,
                                    str(self.initial_commit),
                                    self.tmpdir / 'repo/sample.kicad_pcb',
                                    output_path)
        self.assertFalse(diff_files(output_path, kicad_files_dir / 'sample1/sample.kicad_pcb'))

    def test_extract_file_from_working_tree(self):
        # ワーキングツリーのファイル抽出
        output_path = self.tmpdir / 'WORK' / 'extract/working_tree.kicad_pcb'
        kidivis.review.extract_file(self.git_repo,
                                    None,
                                    self.tmpdir / 'repo/sample.kicad_pcb',
                                    output_path)
        self.assertFalse(diff_files(output_path, kicad_files_dir / 'sample3/sample.kicad_pcb'))

class TestSVGOperations(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix='kidivis'))
        print(f'temporary directory: {self.tmpdir}')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    @unittest.skip('skip test_export_svgs because it takes too long time.')
    def test_export_svgs(self):
        kidivis.review.export_svgs(self.tmpdir, kicad_files_dir / 'sample3/sample.kicad_pcb')
        for layer in ['F_Cu', 'F_Mask', 'B_Cu', 'B_Mask', 'Edge_Cuts']:
            self.assertTrue((self.tmpdir / f'sample-{layer}.svg').exists())

    def test_make_pcbsvg_filename(self):
        name_fcu = kidivis.review.make_pcbsvg_filename(Path('foo.kicad_pcb'), 'F.Cu')
        self.assertEqual(name_fcu, 'foo-F_Cu.svg')

class TestSchOperations(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix='kidivis'))
        print(f'temporary directory: {self.tmpdir}')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_property_regex(self):
        m = kidivis.review.SCH_PROPERTY_PAT.match(
            '(property "Sheetfile" "analog.kicad_sch"')
        self.assertIsNotNone(m)
        self.assertEqual(m.group('name'), 'Sheetfile')
        self.assertEqual(m.group('value'), 'analog.kicad_sch')

    def test_get_sch_subsheets(self):
        self.assertEqual(
            kidivis.review.get_sch_subsheets(kicad_files_dir / 'sample1/sample.kicad_sch'),
            [])

        self.assertEqual(
            kidivis.review.get_sch_subsheets(kicad_files_dir / 'have_subsheets/have_subsheets.kicad_sch'),
            [kidivis.review.KicadSheet('Digital Block', 'digitalblk.kicad_sch')])

        self.assertEqual(
            kidivis.review.get_sch_subsheets(kicad_files_dir / 'have_subsheets/digitalblk.kicad_sch'),
            [kidivis.review.KicadSheet('Display', 'display.kicad_sch'),
             kidivis.review.KicadSheet('Empty Sheet', 'EMPTY.kicad_sch')])

    def test_get_sch_subsheets_recursive(self):
        self.assertEqual(
            kidivis.review.get_sch_subsheets_recursive(
                kicad_files_dir / 'have_subsheets/have_subsheets.kicad_sch'),
            [kidivis.review.KicadSheet('Digital Block', 'digitalblk.kicad_sch'),
             kidivis.review.KicadSheet('Display', 'display.kicad_sch'),
             kidivis.review.KicadSheet('Empty Sheet', 'EMPTY.kicad_sch')])

class TestCommandLineInterface(unittest.TestCase):
    def test_find_kicad_pro_from_dir(self):
        self.assertEqual(kidivis.review.find_kicad_pro_from_dir(kicad_files_dir / 'sample1'),
                         kicad_files_dir / 'sample1/sample.kicad_pro')

    def test_determine_pcb_sch_from_pro(self):
        d = kicad_files_dir / 'sample1'

        pcb_path, sch_path = kidivis.review.determine_pcb_sch_from_pro(d / 'sample.kicad_pro')
        self.assertEqual(pcb_path, d / 'sample.kicad_pcb')
        self.assertEqual(sch_path, d / 'sample.kicad_sch')

    def test_determine_pcb_sch(self):
        d = kicad_files_dir / 'sample1'

        # .kicad_sch を指定
        pcb_path, sch_path = kidivis.review.determine_pcb_sch([d / 'sample.kicad_sch'])
        self.assertIsNone(pcb_path)
        self.assertEqual(sch_path, d / 'sample.kicad_sch')

        # .kicad_pro を指定すると pcb と sch が自動的に決まる
        pcb_path, sch_path = kidivis.review.determine_pcb_sch([d / 'sample.kicad_pro'])
        self.assertEqual(pcb_path, d / 'sample.kicad_pcb')
        self.assertEqual(sch_path, d / 'sample.kicad_sch')

        # .kicad_pro を含むディレクトリを指定することもできる
        pcb_path, sch_path = kidivis.review.determine_pcb_sch([d])
        self.assertEqual(pcb_path, d / 'sample.kicad_pcb')
        self.assertEqual(sch_path, d / 'sample.kicad_sch')

        with self.assertRaises(ValueError):
            # 異なるディレクトリを指定すると例外発生
            kidivis.review.determine_pcb_sch([
                kicad_files_dir / 'sample1/sample.kicad_pro',
                kicad_files_dir / 'sample2/sample.kicad_sch'])

        # .kicad_pro と .kicad_pcb/sch を同時に指定すると .kicad_pcb/sch が優先される
        pcb_path, sch_path = kidivis.review.determine_pcb_sch([
            d / 'sample.kicad_pro', d / 'foo.kicad_sch'])
        self.assertEqual(pcb_path, d / 'sample.kicad_pcb')
        self.assertEqual(sch_path, d / 'foo.kicad_sch')

if __name__ == '__main__':
    unittest.main()
