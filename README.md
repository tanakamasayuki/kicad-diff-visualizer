# kicad-diff-visualizer
A tool to visualize differences of two PCB patterns created by KiCad.

This tool recognizes a Git repository and visualizes the difference between two commits.
Typically it can be used
- when you write a commit log. You can recall what you've done on your PCB design.
- when you check a commit history. It's hard to understand the actual changes based solely on text diffs.

## Requirements

- GitPython >= 3.0
  - Ubuntu: `sudo apt install python3-git`
- Jinja >= 2.10
  - Ubuntu: `sudo apt install python3-jinja2`

## Screenshot

![](doc/screenshot_server.png)

The server is showing the difference of the PCB design.
- White area means no diff.
- Red/blue area is only in the old/new design.

## How to use

    $ ./run_server.sh /path/to/kicad_pcb

Then, open http://localhost:8000/ with a Web browser.
