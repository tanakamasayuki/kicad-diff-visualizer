#!/bin/sh
if [ $# -lt 1 ]
then
  echo Usage: $0 PCB_FILE
  exit 1
fi

pcb_file=$1
PYTHONPATH=./src python3 -m kidivis.review $pcb_file
