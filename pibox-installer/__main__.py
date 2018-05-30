import argparse
import sys
import runpy

from backend.admin import run_as_admin


def get_callback(module, pop=False):
    def _cb():
        if pop:
            sys.argv.pop(1)
        runpy.run_module(module)
    return _cb


if len(sys.argv) == 1:
    run_as_admin(get_callback("gui"), from_gui=True)
elif sys.argv[1] == "cli":
    run_as_admin(get_callback(sys.argv[1], True))
elif sys.argv[1] == "image":
    # master image creation does not require admin privileges
    get_callback(sys.argv[1], True)()
else:
    parser = argparse.ArgumentParser(description="ideascube/kiwix installer for raspberrypi.")
    sub_parser = parser.add_subparsers()
    sub_parser.add_parser("cli", help="run CLI mode")
    sub_parser.add_parser("image", help="prepare a base image")
    parser.parse_args()
