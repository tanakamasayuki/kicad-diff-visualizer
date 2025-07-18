#!/usr/bin/python3

import argparse
import http.server
from itertools import product
import logging
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import uuid

import git
import jinja2

from . import diffimg

LAYERS = ['.'.join(p) for p in product(['F', 'B'], ['Cu', 'Silkscreen', 'Mask'])] + ['Edge.Cuts']
KICAD_CLI = '/mnt/c/Program Files/KiCad/9.0/bin/kicad-cli.exe'

logger = logging.getLogger(__name__)

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
        logger.error('failed to export SVGs: args=%s', res.args)
        res.check_returncode()

def extract_file(git_repo, commit_id, file_path, dst_path):
    logger.debug('extracting file: commit=%s file=%s dst=%s', commit_id, file_path, dst_path)
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

def action_image(req, diff_base, diff_target, filename):
    if not filename.endswith('.svg'):
        req.send_error(http.HTTPStatus.NOT_FOUND)
        return

    layer = filename[:-4]

    base_dir = req.tmp_dir_path / diff_base
    target_dir = req.tmp_dir_path / diff_target
    pcb_filename = req.pcb_path.name

    base_pcb_path = base_dir / pcb_filename
    target_pcb_path = target_dir / pcb_filename
    extract_file(req.git_repo,
                 diff_base,
                 req.pcb_path,
                 base_pcb_path)
    extract_file(req.git_repo,
                 None if diff_target == 'WORK' else diff_target,
                 req.pcb_path,
                 target_pcb_path)

    base_svg_path = base_dir / make_svg_filename(req.pcb_path.name, layer)
    target_svg_path = target_dir / make_svg_filename(req.pcb_path.name, layer)

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
        logger.warning('overlayed_svg does not start with "<svg": %s', overlayed_svg[:10])

    encoded_svg = overlayed_svg.encode('utf-8')

    req.send_response(200)
    req.send_header('Content-Type', 'image/svg+xml')
    req.send_header('Content-Length', len(encoded_svg))
    req.end_headers()
    req.wfile.write(encoded_svg)

def action_diff(req, diff_base, diff_target, layer):
    if layer not in LAYERS:
        req.send_error(http.HTTPStatus.NOT_FOUND)
        return

    t = req.jinja_env.get_template('diffpcb.html')
    s = t.render(base_commit_id=diff_base, target_commit_id=diff_target, layer=layer).encode('utf-8')
    req.send_response(200)
    req.send_header('Content-Type', 'text/html')
    req.send_header('Content-Length', len(s))
    req.end_headers()
    req.wfile.write(s)

class HTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    timeout = 0.5
    '''
    ThreadingHTTPServerを使う方が本質的な解消ができると思うが、
    マルチスレッドの複雑さやログが入り乱れることを避けるために
    ソケットのタイムアウト設定で凌ぐことにする。
    '''

    def __init__(self, tmp_dir_path, git_repo, jinja_env, pcb_path, *args, **kwargs):
        self.tmp_dir_path = tmp_dir_path
        self.git_repo = git_repo
        self.jinja_env = jinja_env
        self.pcb_path = pcb_path
        self.traceid = uuid.uuid4()

        logger.debug('HTTPRequestHandler.__init__(%s): args=%s kwargs=%s', self.traceid, args, kwargs)

        # 親クラスの __init__ は、その中で do_x が実行されるため、最後に呼び出す
        super().__init__(*args, **kwargs)

    def do_GET(self):
        logger.info('do_GET path=%s traceid=%s', self.path, self.traceid)
        try:
            parts = urllib.parse.urlparse(self.path)

            if parts.path == '/':
                self.send_response(http.HTTPStatus.MOVED_PERMANENTLY)
                self.send_header('Location', '/diff/HEAD/WORK/F.Cu')
                self.end_headers()
                return

            path = Path(parts.path)
            num_parts = len(path.parts)

            if path.parts[0] != '/' or num_parts <= 1:
                self.send_error(http.HTTPStatus.NOT_FOUND)
                return

            action = path.parts[1]
            if (action == 'image' or action == 'diff') and num_parts != 5:
                self.send_error(http.HTTPStatus.NOT_FOUND)
                return

            args = [urllib.parse.unquote(p) for p in path.parts[2:]]
            if action == 'image':
                action_image(self, *args)
                return
            elif action == 'diff':
                action_diff(self, *args)
                return

            self.send_error(http.HTTPStatus.NOT_FOUND)
            return

        finally:
            logger.debug('do_GET end. path=%s traceid=%s', self.path, self.traceid)

def handler_factory(*f_args, **f_kwargs):
    def create(*args, **kwargs):
        return HTTPRequestHandler(*f_args, *args, **f_kwargs, **kwargs)
    return create

LOG_LEVELS = ['debug', 'info', 'warning', 'error', 'critical']

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', default=8000, type=int, help='server port number')
    p.add_argument('--host', default='0.0.0.0', help='server host address')
    p.add_argument('--log-level', default='info', choices=LOG_LEVELS, help='change logging level')
    p.add_argument('pcb_file', help='A path to .kicad_pcb file to be reviewed')
    args = p.parse_args()

    log_level = getattr(logging, args.log_level.upper())
    logging.basicConfig(level=log_level, format='%(asctime)-15s %(levelname)s:%(name)s:%(message)s')
    print(f'log level {logger.level}')

    git_repo = git.Repo(args.pcb_file, search_parent_directories=True)

    # Git ワーキングツリーのルート
    git_root = Path(git_repo.working_tree_dir)
    logger.info('git work tree: %s', git_root)

    with tempfile.TemporaryDirectory(prefix='kidivis') as td:
        tmp_dir_path = Path(td)
        logger.info('temporary directory: %s', tmp_dir_path)

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
