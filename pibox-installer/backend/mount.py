#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import re
import sys
import string
import random
import tempfile
import subprocess

from data import data_dir
from backend.util import subprocess_pretty_check_call, subprocess_pretty_call

if sys.platform == "win32":
    imdiskinst = os.path.join(data_dir, 'imdiskinst')
    # imdisk installs in System32 on all platforms
    system32 = os.path.join(os.environ['SystemRoot'], 'System32')
    imdisk_exe = os.path.join(system32, 'imdisk.exe')


def system_has_exfat():
    try:
        with open('/proc/filesystems', 'r') as f:
            return 'exfat' in [line.rstrip().split('\t')[1]
                               for line in f.readlines()]
    except Exception:
        pass
    return False


if sys.platform == "linux":
    mount_exfat = ['mount', '-t', 'exfat'] if system_has_exfat() \
        else [os.path.join(data_dir, 'mount.exfat-fuse')]


def install_imdisk(logger=None, force=False):
    ''' install imdisk manually (replacating steps from install.cmd) '''

    # assume already installed
    if os.path.exists(imdisk_exe) and not force:
        return

    # install the driver and files
    cwd = os.getcwd()
    try:
        os.chdir(imdiskinst)
        ret, _ = subprocess_pretty_call([
            os.path.join(system32, 'rundll32.exe'),
            'setupapi.dll,InstallHinfSection',
            'DefaultInstall', '132',  '.\\imdisk.inf'])
    except Exception:
        ret = 1
    finally:
        os.chdir(cwd)

    if ret != 0:
        raise OSError("Unable to install ImDisk driver. "
                      "Please reboot your computer and retry")

    # start services
    failed = []
    for service in ('imdsksvc', 'awealloc', 'imdisk'):
        if subprocess_pretty_call(['net', 'start', service])[0] != 0:
            failed.append(service)
    if failed:
        raise OSError("ImDisk installed but some "
                      "service/driver failed to start:  {}.\n"
                      "Please reboot your computer and retry"
                      .format(" ".join(failed)))


def install_imdisk_via_cmd(logger=None):
    ''' install imdisk via its .cmd file (silent mode)

        doesn't provide much feedback '''
    os.environ['IMDISK_SILENT_SETUP'] = "1"
    cwd = os.getcwd()
    try:
        os.chdir(imdiskinst)
        subprocess.check_call(['cmd.exe', 'install.cmd'], logger)
    except Exception:
        pass
    finally:
        os.chdir(cwd)


def uninstall_imdisk(logger=None):
    os.environ['IMDISK_SILENT_SETUP'] = "1"
    cwd = os.getcwd()
    try:
        os.chdir(imdiskinst)
        subprocess_pretty_check_call(
            ['cmd.exe', 'uninstall_imdisk.cmd'], logger)
    except Exception:
        pass
    finally:
        os.chdir(cwd)


def get_avail_drive_letter(logger=None):
    ''' returns a free Windows drive letter to mount image in '''
    if not sys.platform == "win32":
        raise NotImplementedError("only for windows")

    wmic_out = subprocess_pretty_call(['wmic', 'logicaldisk', 'get',
                                       'caption'], logger,
                                      check=True, decode=True)
    volumes = [line.strip()[:-1] for line in wmic_out[1:-1]]

    # get list of network mappings
    net_out = subprocess_pretty_call(['net', 'use'],
                                     logger, check=True, decode=True)
    reg = r'\s+([A-Z])\:\s+\\'
    net_maps = [re.match(reg, line).groups()[0]
                for line in net_out if re.match(reg, line)]

    used = sorted(list(set(['A', 'B', 'C'] + volumes + net_maps)))

    for letter in string.ascii_uppercase:
        if letter not in list(used):
            return "{}:".format(letter)


def test_mount_procedure(image_fpath, logger=None, thorough=False):
    ''' whether we are able to mount and unmount data partition

        usefull to ensure setup is OK before starting process
        `thorough` param tests it in two passes writing/checking a file '''

    if sys.platform == "win32":
        install_imdisk(logger)  # make sure we have imdisk installed

    try:
        mount_point, device = mount_data_partition(image_fpath, logger)

        if thorough:
            # write a file on the partition
            value = random.randint(0, 1000)
            with open(os.path.join(mount_point, '.check-part'), 'w') as f:
                f.write(str(value))
            # unmount partitition
            unmount_data_partition(mount_point, device, logger)

            # remount partition
            mount_point, device = mount_data_partition(image_fpath, logger)

            # read the file and check it's what we just wrote
            with open(os.path.join(mount_point, '.check-part'), 'r') as f:
                return int(f.read()) == value
    except Exception:
        return False
    finally:
        try:
            # unmount partition
            unmount_data_partition(mount_point, device, logger)
        except NameError:
            pass  # was not mounted
        except Exception:
            pass  # failed to unmount (outch)


def mount_data_partition(image_fpath, logger=None):
    ''' mount the QEMU image and return its mount point/drive '''

    if sys.platform == "linux":
        losetup_out = subprocess.check_output([
            'losetup', '--partscan',
            '--show', '--find', image_fpath]).decode('utf-8', 'ignore')
        target_dev = str(losetup_out.strip())
        target_part = "{dev}p3".format(dev=target_dev)
        mount_point = tempfile.mkdtemp()
        subprocess.check_call(mount_exfat + [target_part, mount_point])
        return mount_point, target_dev

    elif sys.platform == "darwin":
        # attach image to create pseudo devices
        hdiutil_out = subprocess.check_output(
            ['hdiutil', 'attach', '-nomount', image_fpath]) \
            .decode('utf-8', 'ignore')
        target_dev = str(hdiutil_out.splitlines()[0].split()[0])
        target_part = "{dev}s3".format(dev=target_dev)
        mount_point = tempfile.mkdtemp()
        subprocess.check_call(['mount', '-t', 'exfat',
                              target_part, mount_point])
        return mount_point, target_dev

    elif sys.platform == "win32":
        # make sure we have imdisk installed
        install_imdisk(logger)

        # get an available letter
        target_dev = get_avail_drive_letter(logger)
        mount_point = "{}\\".format(target_dev)
        subprocess_pretty_check_call([
            imdisk_exe, '-a', '-f', image_fpath,
            '-o', 'rw', '-t', 'file', '-v', '3', '-m', target_dev], logger)
        return mount_point, target_dev


def unmount_data_partition(mount_point, device, logger=None):
    ''' unmount data partition and free virtual resources '''

    if sys.platform == "linux":
        subprocess.call(['umount', mount_point])
        os.rmdir(mount_point)
        subprocess.call(['losetup', '-d', device])

    elif sys.platform == "darwin":
        subprocess.call(['umount', mount_point])
        os.rmdir(mount_point)
        subprocess.call(['hdiutil', 'detach', device])
    elif sys.platform == "win32":
        subprocess_pretty_call([imdisk_exe, '-D', '-m', device], logger)
