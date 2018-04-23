#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

''' prepares a base raspbian image into a pibox-kiwix one via QEMU
    - changes sources.list
    - enables SSH
    - copies ansiblecube into the guest
    - run ansiblecube with default values
    - adds /data partition to fstab
'''

from __future__ import (unicode_literals, absolute_import,
                        division, print_function)
import os
import re
import sys
import signal
import threading

import qemu
import ansiblecube

try:
    text_type = unicode  # Python 2
except NameError:
    text_type = str      # Python 3

_vexpress_boot_dir = "pibox-installer-vexpress-boot"
vexpress_boot_kernel = os.path.join(_vexpress_boot_dir, "zImage")
vexpress_boot_dtb = os.path.join(_vexpress_boot_dir,
                                 "vexpress-v2p-ca15_a7.dtb")
ansiblecube_path = os.path.join("ansiblecube")


class Logger:
    @classmethod
    def step(cls, step):
        print("\033[00;34m--> " + step + "\033[00m")

    @classmethod
    def err(cls, err):
        print("\033[00;31m" + err + "\033[00m")

    @classmethod
    def raw_std(cls, std):
        sys.stdout.write(std)

    @classmethod
    def std(cls, std):
        print(std)


# Thread safe class to register pid to cancel in case of abort
class CancelEvent:
    def __init__(self):
        self._lock = threading.Lock()
        self._pids = []

    def lock(self):
        return _CancelEventRegister(self._lock, self._pids)

    def cancel(self):
        self._lock.acquire()
        for pid in self._pids:
            os.kill(pid, signal.SIGTERM)


class _CancelEventRegister:
    def __init__(self, lock, pids):
        self._lock = lock
        self._pids = pids

    def __enter__(self):
        self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._lock.release()

    def register(self, pid):
        if self._pids.count(pid) == 0:
            self._pids.append(pid)

    def unregister(self, pid):
        self._pids.remove(pid)


def run_in_qemu(image_building_path, qemu_binary, qemu_ram,
                logger, cancel_event):

    image_final_path = image_building_path.replace('-BUILDING', '')
    image_error_path = image_building_path.replace('-BUILDING', '-ERROR')

    try:
        # Instance emulator
        emulator = qemu.Emulator(vexpress_boot_kernel,
                                 vexpress_boot_dtb,
                                 image_building_path,
                                 qemu_binary,
                                 qemu_ram,
                                 logger)

        # Run emulation
        with emulator.run(cancel_event) as emulation:

            # fix sources.list
            logger.step("Fix sources.list")
            emulation.exec_cmd(
                "sudo sed -i s/mirrordirector/archive/ /etc/apt/sources.list")

            # enable SSH for good
            logger.step("Enable SSH")
            emulation.exec_cmd("sudo /bin/systemctl enable ssh")

            logger.step("Copy ansiblecube")
            ansiblecube_emulation_path = "/var/lib/ansible/local"
            emulation.exec_cmd("sudo mkdir --mode 0755 -p /var/lib/ansible/")
            emulation.put_dir(ansiblecube_path,
                              ansiblecube_emulation_path)

            # Run ansiblecube
            logger.step("Run ansiblecube")
            ansiblecube.run(
                machine=emulation,
                name="default",
                timezone="UTC",
                wifi_pwd=None,
                edupi=False,
                wikifundi=None,
                aflatoun=False,
                kalite=None,
                zim_install=[],
                ansiblecube_path=ansiblecube_emulation_path,
                admin_account=None)

            # add /data partition to /etc/fstab
            logger.step("Add auto-mount for /data")
            blkid = emulation.exec_cmd("sudo blkid /dev/mmcblk0p3",
                                       capture_stdout=True)
            if 'PARTUUID' in blkid:
                part_uuid = re.findall(r'PARTUUID="([a-z0-9\-]+)"', blkid)[-1]
                emulation.exec_cmd(
                    "sudo sh -c 'echo \"PARTUUID={partid} /data "
                    "exfat defaults,noatime 0 1\" >> /etc/fstab'"
                    .format(partid=part_uuid))

    except Exception as e:
        raise
        # Set final image filename
        if os.path.isfile(image_building_path):
            os.rename(image_building_path, image_error_path)

        logger.step("Failed")
        logger.err(text_type(e))
        error = e
    else:
        # Set final image filename
        os.rename(image_building_path, image_final_path)

        logger.step("Done")
        error = None

    return error


def main(image_building_path, qemu_path='.', qemu_ram='2G'):
    print("starting with target:", image_building_path)

    if not os.path.exists(image_building_path):
        raise IOError("image path does not exists: {}"
                      .format(image_building_path))

    cancel_event = CancelEvent()
    error = run_in_qemu(
        image_building_path,
        os.path.join(qemu_path, "qemu-system-arm"),
        qemu_ram,
        Logger, cancel_event)

    if error:
        print("ERROR: unable to properly create image")
        print(error)
        sys.exit(1)

    print("SUCCESS!", "Image built successfuly")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: {} image_path [qemu_bin_folder qemu_ram]"
              .format(sys.argv[0]))
        sys.exit(1)

    main(*sys.argv[1:])
