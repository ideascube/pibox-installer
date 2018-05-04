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
import shutil
import zipfile
import argparse
import datetime
import urllib.request

import data
from backend.qemu import Emulator
from backend.ansiblecube import (
    run_for_image, ansiblecube_path as ansiblecube_emulation_path)
from util import CLILogger, CancelEvent, get_md5, ReportHook

RASPBIAN_VERSION = "2017-07-05/2017-07-05-raspbian-jessie-lite"
RASPBIAN_URL = ("http://downloads.raspberrypi.org/raspbian_lite/images/"
                "raspbian_lite-{version}.zip".format(version=RASPBIAN_VERSION))
RASPBIAN_ZIP_MD5 = "04452e4298177b08e2050250ee54a40d"


def run_in_qemu(image_fpath, disk_size, root_size,
                qemu_ram, logger, cancel_event):

    logger.step("starting QEMU")
    try:
        # Instance emulator
        emulator = Emulator(data.vexpress_boot_kernel,
                            data.vexpress_boot_dtb,
                            image_fpath,
                            qemu_ram,
                            logger)

        logger.step("resizing QEMU image to {}GB".format(disk_size))
        emulator.resize_image(disk_size * 2 ** 30)

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
            emulation.put_dir(data.ansiblecube_path,
                              ansiblecube_emulation_path)
            emulation.exec_cmd("sudo chown pi:pi -R /var/lib/ansible/")

            # Run ansiblecube
            logger.step("Run ansiblecube")
            run_for_image(machine=emulation)

    except Exception as e:
        logger.step("Failed")
        logger.err(str(e))
        error = e
        raise
    else:
        logger.step("Done")
        error = None

    return error


def main(disk_size, root_size, build_folder, qemu_ram, image_fname=None):

    try:
        root_size = int(root_size)
        disk_size = int(disk_size)

        if root_size <= 2:
            raise ValueError("root partition must be greater than 2GB")

        if root_size > disk_size:
            raise ValueError("root partition can't exceed disk size")
    except Exception as exp:
        CLILogger.err("Erroneous size option: {}".format(repr(exp)))
        sys.exit(1)

    if image_fname is None:
        image_fname = "pibox-kiwix_{date}.img".format(
            date=datetime.datetime.now().strftime("%Y-%m-%d"))
    image_fpath = os.path.join(build_folder, image_fname)

    print("starting with target:", image_fpath)

    zip_fname = os.path.basename(RASPBIAN_URL)
    zip_fpath = os.path.join(build_folder, zip_fname)
    img_fname = zip_fname.replace('.zip', '.img')

    # download raspbian
    if not os.path.exists(zip_fpath) or get_md5(zip_fpath) != RASPBIAN_ZIP_MD5:
        CLILogger.step("Downloading raspbian image file")
        hook = ReportHook(CLILogger.raw_std).reporthook
        try:
            urllib.request.urlretrieve(
                url=RASPBIAN_URL, filename=zip_fpath, reporthook=hook)
        except Exception as exp:
            print("Failed to download raspbian. exiting. {}".format(exp))
            sys.exit(1)
    else:
        CLILogger.step("Reusing already downloaded raspbian ZIP file")

    # extract raspbian and rename
    CLILogger.step("Extracting raspbian image from ZIP file")
    with zipfile.ZipFile(zip_fname) as zipFile:
        extraction = zipFile.extract(img_fname, build_folder)
        shutil.move(extraction, image_fpath)

    if not os.path.exists(image_fpath):
        raise IOError("image path does not exists: {}"
                      .format(image_fpath))

    cancel_event = CancelEvent()
    error = run_in_qemu(
        image_fpath,
        disk_size,
        root_size,
        qemu_ram,
        CLILogger, cancel_event)

    if error:
        print("ERROR: unable to properly create image")
        print(error)
        sys.exit(1)

    print("SUCCESS!", image_fpath, "was built successfuly")


parser = argparse.ArgumentParser(description="pibox base image creator")
parser.add_argument("--root", help="root partition size (GB)", default=3)
parser.add_argument("--size", help="SD card size (GB)", default=4)
parser.add_argument("--build", help="Folder to create files in",
                    default=os.path.abspath('.'))
parser.add_argument("--ram", help="Max RAM for QEMU", default="2G")
parser.add_argument("--out", help="Base image filename (inside --build)")
args = parser.parse_args()

main(disk_size=args.size, root_size=args.root,
     build_folder=args.build, qemu_ram=args.ram, )
