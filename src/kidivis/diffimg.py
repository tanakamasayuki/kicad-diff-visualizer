#!/usr/bin/python3

'''
Copyright (c) 2025 Kota UCHIDA

A tool to create an image showing difference of two PCB patterns.
'''

import argparse
import difflib
import re
import sys

XML_PAT = re.compile('<\\?xml[^>]*>', re.MULTILINE)
SVG_PAT = re.compile('<svg[^>]*>', re.MULTILINE)
SVGEND_PAT = re.compile('</svg>', re.MULTILINE)
STYLE_PAT = re.compile('style="([^"]*)"', re.MULTILINE)
TAG_PAT = re.compile('<(?P<tag>[^/ >]+)(?P<attr>[^>]*)>', re.MULTILINE)

def extract_svg_inner(file_content, only_svg_tag):
    m = XML_PAT.match(file_content)
    if not m:
        print('file must start with <?xml', file=sys.stderr)
        sys.exit(1)
    xml_end = m.end()

    m = SVG_PAT.search(file_content[xml_end:])
    if not m:
        print('not found <svg>', file=sys.stderr)
        sys.exit(1)
    svg_start = xml_end + m.start()
    svg_end = xml_end + m.end()
    svg = file_content[svg_start:svg_end]

    # ファイル先頭から <svg ..> までを取り出す
    head = file_content[(svg_start if only_svg_tag else 0):svg_end]

    # <svg>...</svg> で囲まれる範囲を svg_end/svgend_start に設定

    m = SVGEND_PAT.search(file_content[svg_end:])
    if not m:
        print('not found </svg>', file=sys.stderr)
        sys.exit(1)

    svgend_start = svg_end + m.start()
    inner = file_content[svg_end:svgend_start]

    return head, inner

def decode_style(style_str):
    items = [i.strip() for i in style_str.split(';')]
    items = [i for i in items if len(i) > 0]
    style_dict = {}
    for item in items:
        k,v = item.split(':', 1)
        style_dict[k] = v
    return style_dict

def encode_style(style_dict):
    items = [f'{k}:{v};' for k,v in style_dict.items()]
    return ' '.join(items)

def replace_gstyle_all(svg_content, replace_map):
    new_content = ''
    pos = 0
    while pos < len(svg_content):
        m = TAG_PAT.search(svg_content, pos)
        if not m:
            break
        new_content += svg_content[pos:m.start()]
        pos = m.end()

        tag = m.group('tag')
        attr = m.group('attr')

        m = STYLE_PAT.search(attr)
        if m:
            style = m.group(1)
            style_dict = decode_style(style)
            prefix = attr[:m.start(1)]
            postfix = attr[m.end(1):]
        else:
            style_dict = {}
            prefix = ' style="'
            postfix = '"' + attr

        for key, value in replace_map.items():
            style_dict[key] = value

        new_content += f'<{tag}{prefix}{encode_style(style_dict)}{postfix}>'

    return new_content + svg_content[pos:]

def overlay_two_svgs(bottom_svg, top_svg, only_svg_tag):
    head_old, svg_inner_old = extract_svg_inner(bottom_svg, only_svg_tag)
    head_new, svg_inner_new = extract_svg_inner(top_svg, only_svg_tag)

    if head_old != head_new:
        print('warning: file headers are different', file=sys.stderr)
        diff = difflib.unified_diff(head_old.split(), head_new.split())
        print('\n'.join(diff), file=sys.stderr)
        print('----', file=sys.stderr)

    old_style = {
        'fill': '#ff0000',
        'stroke': '#ff0000',
    }
    new_style = {
        'fill': '#00ffff',
        'stroke': '#00ffff',
    }

    svg_old_replaced = replace_gstyle_all(svg_inner_old, old_style)
    svg_new_replaced = replace_gstyle_all(svg_inner_new, new_style)

    return '\n'.join([
        head_old,
        '<g id="bottom-g">',
        svg_old_replaced,
        '</g>',
        '<g id="top-g" style="mix-blend-mode:normal;">',
        svg_new_replaced,
        '</g>',
        '</svg>',
    ])

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--only-svg-tag', action='store_true',
                   help='Print only <svg> tag. No xml decl or doc type decl.')
    p.add_argument('OLD', help='path to an image of the old pcb')
    p.add_argument('NEW', help='path to an image of the new pcb')
    args = p.parse_args()

    with open(args.OLD) as svgfile:
        old_svg = svgfile.read()

    with open(args.NEW) as svgfile:
        new_svg = svgfile.read()

    print(overlay_two_svgs(old_svg, new_svg, args.only_svg_tag))

if __name__ == '__main__':
    main()
