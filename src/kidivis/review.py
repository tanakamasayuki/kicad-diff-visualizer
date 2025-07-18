#!/usr/bin/python3

import argparse
import http.server
from itertools import product
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.parse

import git
import jinja2

from . import diffimg

LAYERS = ['.'.join(p) for p in product(['F', 'B'], ['Cu', 'Silkscreen', 'Mask'])] + ['Edge.Cuts']
KICAD_CLI = '/mnt/c/Program Files/KiCad/9.0/bin/kicad-cli.exe'

def convert_path_to_windows(file_path):
    path_cmd = ['wslpath', '-w', file_path]
    res = subprocess.run(path_cmd, capture_output=True)
    res.check_returncode()
    return Path(res.stdout.decode('utf-8').strip())

def using_kicadwin_from_wsl():
    '''
    KiCad for Windows を WSL から使う場合に真
    '''
    return Path('/usr/bin/wslpath').exists() and KICAD_CLI.endswith('.exe')

def export_svgs(dst_dir_path, pcb_file_path):
    if using_kicadwin_from_wsl():
        # パスの変換が必要
        if dst_dir_path.drive == '':
            dst_dir_path = convert_path_to_windows(dst_dir_path)
        if pcb_file_path.drive == '':
            pcb_file_path = convert_path_to_windows(pcb_file_path)

    export_cmd = [KICAD_CLI, 'pcb', 'export', 'svg', '--mode-multi',
                  '--fit-page-to-board', '--black-and-white',
                  '--layers', ','.join(LAYERS),
                  '--output', str(dst_dir_path), str(pcb_file_path)]
    res = subprocess.run(export_cmd)
    if res.returncode != 0:
        print(f'failed to export SVGs: args={res.args}')
        res.check_returncode()

def extract_file(git_repo, commit_id, file_path, dst_path):
    print(f'extracting file: commit={commit_id} file={file_path} dst={dst_path}')
    if dst_path.exists():
        return

    dst_path.parent.mkdir(parents=True, exist_ok=True)

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

def make_svg_filename(pcb_file_name, layer_name):
    l = layer_name.replace('.', '_')
    return f'{Path(pcb_file_name).stem}-{l}.svg'

class HTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, tmp_dir_path, git_repo, jinja_env, pcb_path, *args, **kwargs):
        self.tmp_dir_path = tmp_dir_path
        self.git_repo = git_repo
        self.jinja_env = jinja_env
        self.pcb_path = pcb_path

        # 親クラスの __init__ は、その中で do_x が実行されるため、最後に呼び出す
        super().__init__(*args, **kwargs)

    def do_GET(self):
        print(f'do_GET path={self.path}')
        parts = urllib.parse.urlparse(self.path)

        if parts.path == '/':
            self.send_response(http.HTTPStatus.MOVED_PERMANENTLY)
            self.send_header('Location', '/HEAD/WORK/F.Cu')
            self.end_headers()
            return

        path = Path(parts.path)

        if path.parts[0] != '/' or len(path.parts) != 4:
            self.send_response(http.HTTPStatus.NOT_FOUND)
            self.end_headers()
            return

        diff_base, diff_target, layer = [urllib.parse.unquote(p) for p in path.parts[1:]]
        if layer not in LAYERS:
            self.send_response(http.HTTPStatus.NOT_FOUND)
            self.end_headers()
            return

        base_dir = self.tmp_dir_path / diff_base
        target_dir = self.tmp_dir_path / diff_target
        pcb_filename = self.pcb_path.name

        base_pcb_path = base_dir / pcb_filename
        target_pcb_path = target_dir / pcb_filename
        extract_file(self.git_repo,
                     diff_base,
                     self.pcb_path,
                     base_pcb_path)
        extract_file(self.git_repo,
                     None if diff_target == 'WORK' else diff_target,
                     self.pcb_path,
                     target_pcb_path)

        base_svg_path = base_dir / make_svg_filename(self.pcb_path.name, layer)
        target_svg_path = target_dir / make_svg_filename(self.pcb_path.name, layer)

        if not base_svg_path.exists():
            export_svgs(base_dir, base_pcb_path)
        if not target_svg_path.exists():
            export_svgs(target_dir, target_pcb_path)

        with open(base_svg_path) as f:
            base_svg = f.read()
        with open(target_svg_path) as f:
            target_svg = f.read()

        overlayed_svg = diffimg.overlay_two_svgs(base_svg, target_svg, True)
        if overlayed_svg.startswith('<svg'):
            overlayed_svg = overlayed_svg[:4] + ' id="overlayed_svg"' + overlayed_svg[4:]
        else:
            print(f'Waring: overlayed_svg does not start with "<svg": {overlayed_svg[:10]}...')

        t = self.jinja_env.get_template('diffpcb.html')
        s = t.render(svg=overlayed_svg).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', len(s))
        self.end_headers()
        self.wfile.write(s)

def handler_factory(*f_args, **f_kwargs):
    def create(*args, **kwargs):
        return HTTPRequestHandler(*f_args, *args, **f_kwargs, **kwargs)
    return create

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', default=8000, type=int, help='server port number')
    p.add_argument('--host', default='0.0.0.0', help='server host address')
    p.add_argument('pcb_file', help='A path to .kicad_pcb file to be reviewed')
    args = p.parse_args()

    git_repo = git.Repo(args.pcb_file, search_parent_directories=True)

    # Git ワーキングツリーのルート
    git_root = Path(git_repo.working_tree_dir)
    print(f'git work tree: {git_root}')

    with tempfile.TemporaryDirectory(prefix='kidivis') as td:
        tmp_dir_path = Path(td)
        print(f'temporary directory: {tmp_dir_path}')

        jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(Path(__file__).parent / 'templates')),
            autoescape=jinja2.select_autoescape()
        )
        pcb_path = Path(args.pcb_file)
        create_handler = handler_factory(tmp_dir_path, git_repo, jinja_env, pcb_path)
        with http.server.HTTPServer((args.host, args.port), create_handler) as server:
            print(f'Serving HTTP on {args.host} port {args.port}'
                  + f' (http://{args.host}:{args.port}/) ...')
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                input('press enter to exit...')
                raise

    sys.exit(0)


if __name__ == '__main__':
    main()
