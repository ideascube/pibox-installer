#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import sys

from backend.mount import system_has_exfat
if sys.platform == "linux":
    from backend.mount import udisksctl_exe


def host_matches_requirements(build_dir):
    ''' whether the host is ready to start process

        returns bool, str (error message) '''

    # check that build_dir supports file_size > 4GB (not fat)

    if sys.platform == "win32":
        # check that current directory is not on network share (qemu crash)
        pass

    if sys.platform == "linux":
        # udisks2
        if not os.path.exists(udisksctl_exe) or \
                not os.access(udisksctl_exe, os.X_OK):
            return False, "udisks2 (udisksctl) is required."

        # exfat
        mount_exfat = '/sbin/mount.exfat'
        if not system_has_exfat() and (not os.path.exists(mount_exfat) or
                                       not os.access(mount_exfat, os.X_OK)):
            return False, "exfat (kernel module) or exfat-fuse is required."

    return True, None
