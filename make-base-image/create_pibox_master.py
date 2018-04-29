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

from __future__ import (unicode_literals, division, print_function)
import os
import re
import sys

try:
    text_type = unicode  # Python 2
except NameError:
    text_type = str      # Python 3

pibox_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_vexpress_boot_dir = "pibox-installer-vexpress-boot"
vexpress_boot_kernel = os.path.join(pibox_root, _vexpress_boot_dir, "zImage")
vexpress_boot_dtb = os.path.join(pibox_root, _vexpress_boot_dir,
                                 "vexpress-v2p-ca15_a7.dtb")
ansiblecube_path = os.path.join(pibox_root, "ansiblecube")

sys.path.append(os.path.join(pibox_root, 'pibox-installer'))
from backend.ansiblecube import run_for_image, ansiblecube_emulation_path
from backend.qemu import Emulator
from util import CLILogger, CancelEvent


def run_in_qemu(image_building_path, qemu_binary, qemu_ram, resize,
                logger, cancel_event):

    image_final_path = image_building_path.replace('-BUILDING', '')
    image_error_path = image_building_path.replace('-BUILDING', '-ERROR')

    try:
        # Instance emulator
        emulator = Emulator(vexpress_boot_kernel,
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
            emulation.exec_cmd("sudo mkdir --mode 0755 -p /var/lib/ansible/")
            emulation.put_dir(ansiblecube_path, ansiblecube_emulation_path)

            # Run ansiblecube
            logger.step("Run ansiblecube")
            run_for_image(machine=emulation, resize=resize)

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


def main(image_building_path, qemu_path='.', qemu_ram='2G', resize=True):
    print("starting with target:", image_building_path)

    if not os.path.exists(image_building_path):
        raise IOError("image path does not exists: {}"
                      .format(image_building_path))

    cancel_event = CancelEvent()
    error = run_in_qemu(
        image_building_path,
        os.path.join(qemu_path, "qemu-system-arm"),
        qemu_ram,
        bool(resize),
        CLILogger, cancel_event)

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
