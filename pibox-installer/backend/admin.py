#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import sys
import ctypes
import subprocess
try:
    import win32con
except ImportError:
    pass


def is_admin():
    ''' whether current process is ran as Windows Admin or unix root '''
    if sys.platform == "win32":
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False
    return os.getuid() == 0


def run_as_admin(callback, from_gui=False):
    ''' runs specified callback if root otherwise request elevation '''
    if is_admin():
        return callback()
    try:
        if sys.platform == "win32":
            return run_as_win_admin(from_gui)
        elif sys.platform == "darwin":
            return run_as_mac_admin(from_gui)
        elif sys.platform == "linux":
            return run_as_root(from_gui)
        else:
            raise NotImplementedError("O/S `{}` not supported"
                                      .format(sys.platform))
    except PermissionError:
        print("Unable to gain admin access privileges. Exiting.")
        sys.exit(1)


def run_as_win_admin(from_gui):
    # Re-run the program with admin rights
    params = " ".join(['"{}"'.format(x) for x in sys.argv])
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas",
                                             sys.executable,
                                             params, None, 1)
    # ShellExecuteW returns 5 if user chose not to elevate
    if rc == 5:
        raise PermissionError()
    return rc


def run_as_mac_admin(from_gui):
    if from_gui:
        elevation_cmd = [
            '/usr/bin/osascript', '-e',
            "do shell script \"{script} {args} 2>&1\" "
            "with administrator privileges"
            .format(script=sys.executable, args=" ".join(sys.argv))
        ]
        # rc is oascript returns 1 of user could not elevate
        rc = subprocess.call(elevation_cmd)
        if rc == 1:
            raise PermissionError()
        return rc
    else:
        return subprocess.call(['sudo', sys.executable] + sys.argv)


def run_as_root(from_gui):
    elevation_cmd = ['pkexec' if from_gui
                     else 'sudo', sys.executable] + sys.argv
    return subprocess.call(elevation_cmd)
