import filecmp
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

import git

import kidivis.review
import kidivis.repo
from utils import *

class TestRepo(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix='kidivis'))
        print(f'temporary directory: {self.tmpdir}')
        self.extract_dir = self.tmpdir / 'extract'
        self.extract_dir.mkdir()

        kicad_files = ['sample.kicad_' + kind for kind in ['pro', 'sch', 'pcb']]

        git_repo = git.Repo.init(self.tmpdir / 'repo')
        sample_proj_root = Path(git_repo.working_tree_dir) / 'sample'
        sample_proj_root.mkdir()  # KiCad project root directory

        for f in kicad_files:
            shutil.copy(kicad_files_dir / 'sample1' / f, sample_proj_root)
        git_repo.index.add([Path('sample') / f for f in kicad_files])
        self.initial_commit = git_repo.index.commit('initial commit')

        for f in kicad_files:
            shutil.copy(kicad_files_dir / 'sample2' / f, sample_proj_root)
        git_repo.index.add([Path('sample') / f for f in kicad_files])
        self.second_commit = git_repo.index.commit('second commit')

        for f in kicad_files:
            shutil.copy(kicad_files_dir / 'sample3' / f, sample_proj_root)
        # コミットしない。変更がワーキングツリーだけにある状態とする。

        self.git_repo = kidivis.repo.Git(sample_proj_root)
        self.backups_repo = kidivis.repo.Backups(kicad_files_dir / 'have_subsheets')
        self.repo = kidivis.repo.Repo(self.git_repo, self.backups_repo)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_extract_file(self):
        dst_path = self.extract_dir / 'name1/name2.kicad_sch'
        self.repo.extract_file(None, 'sample.kicad_sch', dst_path)
        self.assertFalse(diff_files(dst_path, kicad_files_dir / 'sample3/sample.kicad_sch'))

        dst_path = self.extract_dir / 'name3/name4.kicad_sch'
        self.repo.extract_file('HEAD^', 'sample.kicad_sch', dst_path)
        self.assertFalse(diff_files(dst_path, kicad_files_dir / 'sample1/sample.kicad_sch'))

        # have_subsheets-2025-07-19_113432.zip
        dst_path = self.extract_dir / 'name5/name6.kicad_sch'
        self.repo.extract_file('2025-07-19_113432', 'display.kicad_sch', dst_path)
        zf = zipfile.ZipFile(kicad_files_dir / 'have_subsheets/have_subsheets-backups/have_subsheets-2025-07-19_113432.zip')
        zf.extract('display.kicad_sch', self.tmpdir)
        self.assertFalse(diff_files(dst_path, self.tmpdir / 'display.kicad_sch'))

