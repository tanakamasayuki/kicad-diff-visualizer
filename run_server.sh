#!/bin/sh

# Specify current dir "." if no argument provided
input_files="${@:-.}"

script_dir="$(dirname "$(realpath "$0")")"
PYTHONPATH=$script_dir/src python3 -m kidivis.review $input_files
