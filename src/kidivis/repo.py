'''
Copyright (c) 2025 Kota UCHIDA

Data repository classes. Git or KiCad's backup directory.
'''

import logging
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

import git

BACKUP_DATE_PAT = re.compile(r'\d{4}-\d{2}-\d{2}_\d{6}')

logger = logging.getLogger(__name__)

class Git:
    def __init__(self, kicad_proj_dir):
        self.kicad_proj_dir = kicad_proj_dir
        self.git_repo = git.Repo(self.kicad_proj_dir, search_parent_directories=True)

    def extract_file(self, commit_id, file_name, dst_path):
        '''
        commit_id に含まれる file_name を dst_path へ抽出する。
        commit_id が None なら、ワーキングツリーのファイルをそのまま dst_path へコピーする。
        '''
        file_path = self.kicad_proj_dir / file_name
        logger.debug('extracting file: commit=%s file=%s dst=%s', commit_id, file_path, dst_path)
        if dst_path.exists():
            return

        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if commit_id is None:
            # ワーキングツリーからファイル取得
            shutil.copy(file_path, dst_path)
            return

        rel_path = Path(file_path).relative_to(self.git_repo.working_tree_dir)
        '''
        subprocess を使わなくても git_repo.git.show(f'{commit_id}:{rel_path}') で
        git show を実行可能だが、この場合は git show の出力が bytes ではなく str
        になってしまう。改行コード含め、完全に同じバイナリを取り出したいので、
        subprocess.run を使って bytes のままファイルへ書き出す。
        '''
        git_show_cmd = ['git', 'show', f'{commit_id}:{rel_path}']
        res = subprocess.run(git_show_cmd, capture_output=True, cwd=self.git_repo.working_tree_dir)
        with open(dst_path, 'wb') as f:
            f.write(res.stdout)
            pass

class Backups:
    def __init__(self, kicad_proj_dir):
        self.kicad_proj_dir = kicad_proj_dir
        self.kicad_pro_path = next(kicad_proj_dir.glob('*.kicad_pro'))
        self.backups_dir = self.kicad_proj_dir / (self.kicad_pro_path.stem + '-backups')

    def extract_file(self, version, file_name, dst_path):
        '''
        version が示す zip に含まれる file_path を dst_path へ抽出する。
        version が None なら、ワーキングツリーのファイルをそのまま dst_path へコピーする。
        '''
        zip_name = f'{self.kicad_pro_path.stem}-{version}.zip'
        with zipfile.ZipFile(self.backups_dir / zip_name) as zf:
            with zf.open(file_name) as src:
                with open(dst_path, 'wb') as dst:
                    shutil.copyfileobj(src, dst)

class Repo:
    def __init__(self, git_repo, backups_repo):
        self.git_repo = git_repo
        self.backups_repo = backups_repo

    def extract_file(self, version, file_name, dst_path):
        '''
        version が日付なら backups ディレクトリから、
        日付以外なら Git リポジトリからファイルを抽出する。
        '''
        if version is None or BACKUP_DATE_PAT.match(version) is None:
            return self.git_repo.extract_file(version, file_name, dst_path)
        else:
            return self.backups_repo.extract_file(version, file_name, dst_path)
