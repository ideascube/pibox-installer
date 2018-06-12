#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

''' prepares a base raspbian image into a pibox-kiwix one via QEMU
    - changes sources.list
    - enables SSH
    - copies ansiblecube into the guest
    - run ansiblecube with default values
'''

from __future__ import (unicode_literals, division, print_function)
import os
import sys
import argparse
import datetime

import data
from backend import qemu
from backend.content import get_content
from backend.download import download_content, unzip_file
from backend.ansiblecube import (
    run_for_image, ansiblecube_path as ansiblecube_emulation_path)
from util import CLILogger, CancelEvent, ONE_GB


def run_in_qemu(image_fpath, disk_size, root_size,
                logger, cancel_event, qemu_ram):

    logger.step("starting QEMU")
    try:
        # Instance emulator
        emulator = qemu.Emulator(data.vexpress_boot_kernel,
                                 data.vexpress_boot_dtb,
                                 image_fpath,
                                 logger,
                                 ram=qemu_ram)

        logger.step("resizing QEMU image to {}GB".format(disk_size // ONE_GB))
        emulator.resize_image(disk_size)

        # Run emulation
        with emulator.run(cancel_event) as emulation:
            # enable SSH for good
            logger.step("Enable SSH")
            emulation.exec_cmd("sudo /bin/systemctl enable ssh")

            logger.step("Copy ansiblecube")
            emulation.exec_cmd("sudo mkdir --mode 0755 -p /var/lib/ansible/")
            emulation.put_dir(data.ansiblecube_path,
                              ansiblecube_emulation_path)
            emulation.exec_cmd("sudo chown pi:pi -R /var/lib/ansible/")

            # Run ansiblecube
            logger.step("Run ansiblecube")
            run_for_image(machine=emulation,
                          root_partition_size=root_size,
                          disk_size=disk_size)

    except Exception as e:
        logger.step("Failed")
        logger.err(str(e))
        error = e
        raise
    else:
        logger.step("Done")
        error = None

    return error


def main(logger,
         disk_size, root_size, build_folder, qemu_ram, image_fname=None):

    try:
        root_size = int(root_size) * ONE_GB
        disk_size = int(disk_size) * ONE_GB

        if root_size <= 5:
            raise ValueError("root partition must be greater than 5GB")

        if root_size > disk_size:
            raise ValueError("root partition can't exceed disk size")
    except Exception as exp:
        logger.err("Erroneous size option: {}".format(repr(exp)))
        sys.exit(1)

    if image_fname is None:
        image_fname = "pibox-kiwix_{date}.img".format(
            date=datetime.datetime.now().strftime("%Y-%m-%d"))
    image_fpath = os.path.join(build_folder, image_fname)

    print("starting with target:", image_fpath)

    # download raspbian
    logger.step("Retrieving raspbian image file")
    raspbian_image = get_content('raspbian_image')
    rf = download_content(raspbian_image, logger, build_folder)
    if not rf.successful:
        logger.err("Failed to download raspbian.\n{e}"
                   .format(e=rf.exception))
        sys.exit(1)
    elif rf.found:
        logger.std("Reusing already downloaded raspbian ZIP file")

    # extract raspbian and rename
    logger.step("Extracting raspbian image from ZIP file")
    unzip_file(archive_fpath=rf.fpath,
               src_fname=raspbian_image['name'].replace('.zip', '.img'),
               build_folder=build_folder,
               dest_fpath=image_fpath)
    logger.std("Extraction complete: {p}".format(p=image_fpath))

    if not os.path.exists(image_fpath):
        raise IOError("image path does not exists: {}"
                      .format(image_fpath))

    cancel_event = CancelEvent()
    error = run_in_qemu(
        image_fpath,
        disk_size,
        root_size,
        logger, cancel_event,
        qemu_ram)

    if error:
        print("ERROR: unable to properly create image")
        print(error)
        sys.exit(1)

    print("SUCCESS!", image_fpath, "was built successfuly")


parser = argparse.ArgumentParser(description="pibox base image creator")
parser.add_argument("--root", help="root partition size (GB)", default=5)
parser.add_argument("--size", help="SD card size (GB)", default=8)
parser.add_argument("--build", help="Folder to create files in",
                    default=os.path.abspath('.'))
parser.add_argument("--ram", help="Max RAM for QEMU", default="2G")
parser.add_argument("--out", help="Base image filename (inside --build)")
args = parser.parse_args()

main(logger=CLILogger(),
     disk_size=args.size, root_size=args.root,
     build_folder=args.build, image_fname=args.out,
     qemu_ram=args.ram)
