from backend import ansiblecube
from backend import qemu
from backend.content import get_collection, get_content, get_all_contents_for
from backend.download import download_content, unzip_file
from backend.mount import mount_data_partition, unmount_data_partition
from backend.util import subprocess_pretty_check_call, subprocess_pretty_call
import data
from util import ReportHook, human_readable_size, get_cache
from datetime import datetime
import os
import itertools
import shutil
import data
import sys
import re
import humanfriendly

if sys.platform == "linux":
    from backend.mount import loop_device

def log_duration(logger, started_on, ended_on=None):
    ended_on = datetime.now() if ended_on is None else ended_on
    duration = ended_on - started_on
    logger.std("Duration: {duration}. ({start} to {end}).".format(
        start=started_on, end=ended_on,
        duration=humanfriendly.format_timespan(duration.total_seconds())))

def run_installation(name, timezone, language, wifi_pwd, admin_account, kalite, aflatoun, wikifundi, edupi, zim_install, size, logger, cancel_event, sd_card, favicon, logo, css, done_callback=None, build_dir=".", tap=None):

    started_on = datetime.now()
    logger.std("started on {}".format(started_on))

    try:
        # set image names
        today = datetime.today().strftime('%Y_%m_%d-%H_%M_%S')

        image_final_path = os.path.join(build_dir, "pibox-{}.img".format(today))
        image_building_path = os.path.join(build_dir, "pibox-{}.BUILDING.img".format(today))
        image_error_path = os.path.join(build_dir, "pibox-{}.ERROR.img".format(today))

        # linux needs root to use loop devices
        if sys.platform == "linux":
            subprocess_pretty_check_call(
                ["chmod", "-c", "o+rwx", loop_device], logger, as_admin=True)

        # Prepare SD Card
        if sd_card:
            if sys.platform == "linux":
                subprocess_pretty_check_call(
                    ["chmod", "-c", "o+w", sd_card], logger, as_admin=True)
            elif sys.platform == "darwin":
                subprocess_pretty_check_call(["diskutil", "unmountDisk", sd_card], logger)
                subprocess_pretty_check_call(
                    ["chmod", "-v", "o+w", sd_card], logger, as_admin=True)
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

        # Download Base image
        logger.step("Retrieving pibox base image file")
        base_image = get_content('pibox_base_image')
        rf = download_content(base_image, logger, build_dir)
        if not rf.successful:
            logger.err("Failed to download pibox base image.\n{e}"
                       .format(e=rf.exception))
            sys.exit(1)
        elif rf.found:
            logger.std("Reusing already downloaded base image ZIP file")

        # extract base image and rename
        logger.step("Extracting base image from ZIP file")
        unzip_file(archive_fpath=rf.fpath,
                   src_fname=base_image['name'].replace('.zip', ''),
                   build_folder=build_dir,
                   dest_fpath=image_building_path)
        logger.std("Extraction complete: {p}".format(p=image_building_path))

        if not os.path.exists(image_building_path):
            raise IOError("image path does not exists: {}"
                          .format(image_building_path))

        # harmonize options
        packages = [] if zim_install is None else zim_install
        kalite_languages = [] if kalite is None else kalite
        wikifundi_languages = [] if wikifundi is None else wikifundi
        aflatoun_languages = ['fr', 'en'] if aflatoun else []

        # collection contains both downloads and processing callbacks
        # for all requested contents
        collection = get_collection(
            edupi=edupi,
            packages=packages,
            kalite_languages=kalite_languages,
            wikifundi_languages=wikifundi_languages,
            aflatoun_languages=aflatoun_languages)

        # download contents into cache
        logger.step("Starting all content downloads")
        downloads = get_all_contents_for(collection)

        for dl_content in downloads:
            logger.step("Retrieving {url} ({size})".format(
                url=dl_content['url'],
                size=human_readable_size(dl_content['archive_size'])))

            rf = download_content(dl_content, logger, build_dir)
            if not rf.successful:
                logger.err("Error downloading {u} to {p}\n{e}"
                           .format(u=dl_content['url'],
                                   p=rf.fpath, e=rf.exception))
                if rf.exception:
                    raise rf.exception
            elif rf.found:
                logger.std("Reusing already downloaded {p}".format(p=rf.fpath))
            else:
                logger.std("Saved `{p}` successfuly: {s}"
                           .format(p=dl_content['name'],
                                   s=human_readable_size(rf.downloaded_size)))

        # Instanciate emulator
        logger.step("Preparing qemu VM")
        emulator = qemu.Emulator(data.vexpress_boot_kernel,
                                 data.vexpress_boot_dtb,
                                 image_building_path, logger,
                                 ram="2G", tap=tap)

        # Resize image
        logger.step("Resizing image file to {s}"
                    .format(s=human_readable_size(emulator.get_image_size())))
        if size < emulator.get_image_size():
            logger.err("cannot decrease image size")
            raise ValueError("cannot decrease image size")

        emulator.resize_image(size)

        # prepare ansible options
        ansible_options = {
            'name': name,
            'timezone': timezone,
            'language': language,
            'language_name': dict(data.ideascube_languages)[language],

            'edupi': edupi,
            'wikifundi_languages': wikifundi_languages,
            'aflatoun_languages': aflatoun_languages,
            'kalite_languages': kalite_languages,
            'packages': packages,

            'wifi_pwd': wifi_pwd,
            'admin_account': admin_account,

            'disk_size': emulator.get_image_size(),
            'root_partition_size': base_image.get('root_partition_size'),
        }
        extra_vars, secret_keys = ansiblecube.build_extra_vars(
            **ansible_options)

        # Run emulation
        logger.step("Starting-up VM")
        with emulator.run(cancel_event) as emulation:
            # copying ansiblecube again into the VM
            # should the master-version been updated
            logger.step("Copy ansiblecube")
            emulation.exec_cmd("sudo /bin/rm -rf {}".format(
                ansiblecube.ansiblecube_path))
            emulation.put_dir(data.ansiblecube_path,
                              ansiblecube.ansiblecube_path)

            logger.step("Run ansiblecube")
            ansiblecube.run_phase_one(emulation, extra_vars, secret_keys,
                                      logo=logo, favicon=favicon, css=css)

        # mount image's 3rd partition on host
        logger.step("Mounting data partition on host")
        mount_point, device = mount_data_partition(image_building_path, logger)

        # copy contents from cache to mount point
        try:
            logger.step("Processing downloaded content onto data partition")
            cache_folder = get_cache(build_dir)
            for category, _, content_run_cb, cb_kwargs in collection:
                logger.step("Processing {cat}".format(cat=category))
                content_run_cb(cache_folder=cache_folder,
                               mount_point=mount_point,
                               logger=logger, **cb_kwargs)
        except Exception as e:
            unmount_data_partition(mount_point, device, logger)
            raise e

        # unmount partition
        logger.step("Unmounting data partition")
        unmount_data_partition(mount_point, device, logger)

        # rerun emulation for discovery
        logger.step("Starting-up VM again for content-discovery")
        with emulator.run(cancel_event) as emulation:
            logger.step("Re-run ansiblecube for move-content")
            ansiblecube.run_phase_two(emulation, extra_vars, secret_keys,
                                      seal=False)

        # Write image to SD Card
        if sd_card:
            logger.step("Writting image to SD-card ({card})".format(sd_card))
            emulator.copy_image(sd_card)

    except Exception as e:
        logger.step("Failed")
        logger.err(str(e))
        log_duration(logger, started_on)

        # Set final image filename
        if os.path.isfile(image_building_path):
            os.rename(image_building_path, image_error_path)

        error = e
        raise e
    else:
        # Set final image filename
        os.rename(image_building_path, image_final_path)

        logger.step("Done")
        log_duration(logger, started_on)
        error = None
    finally:
        if sys.platform == "linux":
            subprocess_pretty_call(
                ["chmod", "-c", "o-rwx", loop_device], logger, as_admin=True)
        if sd_card:
            if sys.platform == "linux":
                subprocess_pretty_call(
                    ["chmod", "-c", "o-w", sd_card], logger, as_admin=True)
            elif sys.platform == "darwin":
                subprocess_pretty_call(
                    ["chmod", "-v", "o-w", sd_card], logger, as_admin=True)

    if done_callback:
        done_callback(error)

    return error
