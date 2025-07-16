#!/usr/bin/python3

import argparse
from itertools import product
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import git

LAYERS = ['.'.join(p) for p in product(['F', 'B'], ['Cu', 'Silkscreen', 'Mask'])] + ['Edge.Cuts']
KICAD_CLI = '/mnt/c/Program Files/KiCad/9.0/bin/kicad-cli.exe'

def export_svgs(dst_dir_path, pcb_file_path):
    if KICAD_CLI.endswith('.exe') and not dst_dir_path.drive.startswith(r'\\wsl'):
        # パスの変換が必要
        path_cmd = ['wslpath', '-w', dst_dir_path]
        dst_dir_path = subprocess.run(path_cmd, capture_output=True).stdout.strip()

    export_cmd = [KICAD_CLI, 'pcb', 'export', 'svg', '--mode-multi',
                  '--layers', ','.join(LAYERS),
                  '--output', dst_dir_path, pcb_file_path]
    subprocess.run(export_cmd)

def extract_file(git_repo, commit_id, file_path, dst_path):
    if commit_id is None:
        # ワーキングツリーからファイル取得
        shutil.copy(file_path, dst_path)
        return

    rel_path = Path(file_path).relative_to(git_repo.working_tree_dir)
    '''
    subprocess を使わなくても git_repo.git.show(f'{commit_id}:{rel_path}') で
    git show を実行可能だが、この場合は git show の出力が bytes ではなく str
    になってしまう。改行コード含め、完全に同じバイナリを取り出したいので、
    subprocess.run を使って bytes のままファイルへ書き出す。
    '''
    git_show_cmd = ['git', 'show', f'{commit_id}:{rel_path}']
    res = subprocess.run(git_show_cmd, capture_output=True, cwd=git_repo.working_tree_dir)
    with open(dst_path, 'wb') as f:
        f.write(res.stdout)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', default='HEAD', help='A commit ID for comparison base. Default is HEAD.')
    p.add_argument('--target', help='A commit ID for comparison target. If this is blank, working tree is used.')
    p.add_argument('pcb_file', help='A path to .kicad_pcb file to be reviewed')
    args = p.parse_args()

    git_repo = git.Repo(args.pcb_file, search_parent_directories=True)
    git_cmd = git_repo.git

    # Git ワーキングツリーのルート
    git_root = Path(git_repo.working_tree_dir)
    print(f'git work tree: {git_root}')

    with tempfile.TemporaryDirectory() as td:
        tmp_dir_path = Path(td)
        print(f'temporary directory: {tmp_dir_path}')

        if args.target is None:
            # ワーキングツリーの状態を用いる
            shutil.copy(args.pcb_file, tmp_dir_path / 'new.kicad_pcb')
        else:
            # 指定コミットの内容を使う
            extract_file(git_repo, args.target, args.pcb_file, tmp_dir_path / 'new.kicad_pcb')

        export_svgs(tmp_dir_path, args.pcb_file)

        input('Press enter to exit...')

    sys.exit(0)


if __name__ == '__main__':
    main()
