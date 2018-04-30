from backend import ansiblecube
from backend import qemu
from backend.util import subprocess_pretty_check_call
import data
from util import ReportHook
from datetime import datetime
import os
import urllib.request
import shutil
from zipfile import ZipFile
import data
import sys
import re

def run_installation(name, timezone, language, wifi_pwd, admin_account, kalite, aflatoun, wikifundi, edupi, zim_install, size, logger, cancel_event, sd_card, favicon, logo, css, done_callback=None, build_dir="."):

    try:
        # Prepare SD Card
        if sd_card:
            if sys.platform == "linux":
                #TODO restore sd_card mod
                subprocess_pretty_check_call(["pkexec", "chmod", "-c", "o+w", sd_card], logger)
            elif sys.platform == "darwin":
                #TODO restore sd_card mod
                subprocess_pretty_check_call(["osascript", "-e", "do shell script \"diskutil unmountDisk {0} && chmod -v o+w {0}\" with administrator privileges".format(sd_card)], logger)
            elif sys.platform == "win32":
                matches = re.findall(r"\\\\.\\PHYSICALDRIVE(\d*)", sd_card)
                if len(matches) != 1:
                    raise ValueError("Error while getting physical drive number")
                device_number = matches[0]

                r,w = os.pipe()
                os.write(w, str.encode("select disk {}\n".format(device_number)))
                os.write(w, b"clean\n")
                os.close(w)
                logger.std("diskpart select disk {} and clean".format(device_number))
                subprocess_pretty_check_call(["diskpart"], logger, stdin=r)

        # set image names
        today = datetime.today().strftime('%Y_%m_%d-%H_%M_%S')

        image_final_path = os.path.join(build_dir, "pibox-{}.img".format(today))
        image_building_path = os.path.join(build_dir, "pibox-{}.BUILDING.img".format(today))
        image_error_path = os.path.join(build_dir, "pibox-{}.ERROR.img".format(today))

        # Download Raspbian
        logger.step("Download Raspbian-lite image")
        hook = ReportHook(logger.raw_std).reporthook
        (zip_filename, _) = urllib.request.urlretrieve(data.raspbian_url, reporthook=hook)
        with ZipFile(zip_filename) as zipFile:
            logger.std("extract " + data.raspbian_zip_path)
            extraction = zipFile.extract(data.raspbian_zip_path, build_dir)
            shutil.move(extraction, image_building_path)
        os.remove(zip_filename)

        # Instance emulator
        emulator = qemu.Emulator(data.vexpress_boot_kernel, data.vexpress_boot_dtb, image_building_path, logger)

        # Resize image
        if size < emulator.get_image_size():
            logger.err("cannot decrease image size")
            raise ValueError("cannot decrease image size")

        emulator.resize_image(size)

        # Run emulation
        with emulator.run(cancel_event) as emulation:

            logger.step("Run ansiblecube")
            ansiblecube.run_for_user(
                machine=emulation,
                name=name,
                timezone=timezone,
                language=language,
                language_name=dict(data.ideascube_languages)[language],

                kalite=kalite,
                wikifundi=wikifundi,
                edupi=edupi,
                aflatoun=aflatoun,
                zim_install=zim_install,

                wifi_pwd=wifi_pwd,
                admin_account=admin_account,

                logo=logo,
                favicon=favicon,
                css=css)

        # mount image's 3rd partition on host

        # download contents onto mount point

        # unmount partition

        # rerun emulation for discovery

        # Write image to SD Card
        if sd_card:
            emulator.copy_image(sd_card)

    except Exception as e:
        # Set final image filename
        if os.path.isfile(image_building_path):
            os.rename(image_building_path, image_error_path)

        logger.step("Failed")
        logger.err(str(e))
        error = e
    else:
        # Set final image filename
        os.rename(image_building_path, image_final_path)

        logger.step("Done")
        error = None

    if done_callback:
        done_callback(error)

    return error
