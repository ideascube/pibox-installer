#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import sys
import tempfile
import subprocess


def mount_data_partition(image_fpath):
    ''' mount the QEMU image and return its mount point/drive '''

    if sys.platform == "linux":
        losetup_out = subprocess.check_output([
            'pkexec', 'losetup', '--partscan',
            '--show', '--find', image_fpath])
        target_dev = losetup_out.strip()
        target_part = "{dev}p3".format(dev=target_dev)
        mount_point = tempfile.mkdtemp()
        subprocess.run(['pkexec', 'mount', '-t', 'exfat',
                        target_part, mount_point], check=True)
        return mount_point, target_dev

    elif sys.platform == "darwin":
        # attach image to create pseudo devices
        hdiutil_out = subprocess.check_output(
            ['hdiutil', 'attach', '-nomount', image_fpath]) \
            .decode('utf-8', 'ignore')
        target_dev = str(hdiutil_out.splitlines()[0].split()[0])
        target_part = "{dev}s3".format(dev=target_dev)
        mount_point = tempfile.mkdtemp()
        subprocess.run(['mount', '-t', 'exfat',
                        target_part, mount_point], check=True)
        return mount_point, target_dev

    elif sys.platform == "win32":
        pass


def unmount_data_partition(mount_point, device):
    ''' unmount data partition and free virtual resources '''

    if sys.platform == "linux":
        subprocess.run(['pkexec', 'umount', mount_point], check=False)
        os.rmdir(mount_point)
        subprocess.run(['pkexec', 'losetup', '-d', device], check=False)

    elif sys.platform == "darwin":
        subprocess.run(['umount', mount_point], check=False)
        os.rmdir(mount_point)
        subprocess.run(['hdiutil', 'detach', device], check=False)
    elif sys.platform == "win32":
        pass
