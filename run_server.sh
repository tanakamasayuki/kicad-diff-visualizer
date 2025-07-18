#!/bin/sh
if [ $# -lt 1 ]
then
  echo Usage: $0 [options] PCB_FILE
  exit 1
fi

PYTHONPATH=./src python3 -m kidivis.review "$@"
