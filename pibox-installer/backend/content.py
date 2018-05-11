#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import json
import shutil
import pathlib

from data import content_file
from util import get_temp_folder
from backend.catalog import YAML_CATALOGS
from backend.download import get_content_cache, unarchive

MIRROR = "http://download.kiwix.org"
MIRROR = "http://192.168.1.102:8000"

# prepare CONTENTS from JSON file
with open(content_file, 'r') as fp:
    CONTENTS = json.load(fp)
    for key, dl_data in CONTENTS.items():
        if 'url' in dl_data.keys():
            CONTENTS[key]['url'] = CONTENTS[key]['url'].format(mirror=MIRROR)


def get_content(key):
    return CONTENTS.get(key)


def get_collection(edupi=False,
                   packages=[],
                   kalite_languages=[],
                   wikifundi_languages=[],
                   aflatoun_languages=[]):
    ''' builds a complete list of fnames, url for all content '''

    collection = []

    if edupi:
        collection.append(('EduPi',
                           get_edupi_contents, run_edupi_actions,
                           {'enable': edupi}))

    if len(packages):
        collection.append(('Packages',
                           get_packages_contents, run_packages_actions,
                           {'packages': packages}))

    if len(kalite_languages):
        collection.append(('KA-Lite',
                           get_kalite_contents, run_kalite_actions,
                           {'languages': kalite_languages}))

    if len(wikifundi_languages):
        collection.append(('Wikifundi',
                           get_wikifundi_contents, run_wikifundi_actions,
                           {'languages': wikifundi_languages}))

    if len(aflatoun_languages):
        collection.append(('Aflatoun',
                           get_aflatoun_contents, run_aflatoun_actions,
                           {'languages': aflatoun_languages}))

    return collection


def get_edupi_contents(enable=False):
    ''' edupi: has no large downloads '''
    return []


def get_kalite_contents(languages=[]):
    ''' kalite medium lang packs and huge tarball of videos for each lang '''

    return [
        get_content('kalite_langpack_{lang}'.format(lang=lang))
        for lang in languages] + [

        get_content('kalite_videos_{lang}'.format(lang=lang))
        for lang in languages]


def get_wikifundi_contents(languages=[]):
    ''' wikifundi: large language pack for each lang '''
    return [get_content('wikifundi_langpack_{lang}'.format(lang=lang))
            for lang in languages]


def get_aflatoun_contents(languages=[]):
    ''' aflatoun: single large tarball with content '''
    return [get_content('aflatoun_content')]


def get_package_content(package_id):
    for catalog in YAML_CATALOGS:
        try:
            package = catalog['all'][package_id]
            return {
                "url": package['url'],
                "name": "package_{}".format(package_id),
                "checksum": package['sha256sum'],
                "archive_size": package['size'],
                "expanded_size": package['size'] * 1.10
                if package['type'] != 'zim' else package['size'],
            }
        except IndexError:
            continue


def get_packages_contents(packages=[]):
    ''' ideacube: ZIM files or ZIP file for each package '''
    return [get_package_content(package) for package in packages]


def extract_and_move(content, cache_folder, root_path, final_path):
    # retrieve archive path
    archive_fpath = get_content_cache(content, cache_folder, True)

    # extract to a temp folder on root_path
    extract_folder = get_temp_folder(root_path)
    unarchive(archive_fpath, extract_folder)

    # move useful content to final path
    useful_path = os.path.join(extract_folder, content['folder_name']) \
        if 'folder_name' in content.keys() else extract_folder
    shutil.move(useful_path, final_path)

    # remove temp dir
    shutil.rmtree(extract_folder, ignore_errors=True)


def run_edupi_actions(cache_folder, mount_point, logger, enable=False):
    ''' no action for EduPi ; everything within ansiblecube '''
    return


def run_kalite_actions(cache_folder, mount_point, logger, languages=[]):

    if not len(languages):
        return

    for lang in languages:
        # language pack
        lang_key = 'kalite_langpack_{lang}'.format(lang=lang)
        lang_pack = get_content(lang_key)
        extract_and_move(
            content=lang_pack,
            cache_folder=cache_folder,
            root_path=mount_point,
            final_path=os.path.join(mount_point, lang_key))

        # videos
        videos = get_content('kalitekalite_videos_{lang}'.format(lang=lang))
        extract_and_move(
            content=videos,
            cache_folder=cache_folder,
            root_path=mount_point,
            final_path=os.path.join(mount_point, videos['folder_name']))


def run_wikifundi_actions(cache_folder, mount_point, logger, languages=[]):
    ''' extracts all lang packs to their expected folder on partition '''

    if not len(languages):
        return

    for lang in languages:
        content = get_content('wikifundi_langpack_{lang}'.format(lang=lang))
        extract_and_move(
            content=content,
            cache_folder=cache_folder,
            root_path=mount_point,
            final_path=os.path.join(mount_point, content['folder_name']))


def run_aflatoun_actions(cache_folder, mount_point, logger, languages=[]):
    ''' extracts content.tar.gz to aflatoun_content on partition '''

    if not len(languages):
        return

    extract_and_move(content=get_content('aflatoun_content'),
                     cache_folder=cache_folder,
                     root_path=mount_point,
                     final_path=os.path.join(mount_point, 'aflatoun_content'))


def run_packages_actions(cache_folder, mount_point, logger, packages=[]):
    ''' moves downloaded ZIM files to an expected location on partition '''

    # ensure packages folder exists
    packages_folder = pathlib.Path(os.path.join(mount_point, "packages"))
    packages_folder.mkdir(exist_ok=True)

    for package in packages:
        content = get_package_content(package)
        logger.std("Copying {p} to {f}".format(p=content['name'],
                                               f=packages_folder))

        # retrieve downloaded path
        package_fpath = get_content_cache(content, cache_folder, True)
        # copy to the packages folder
        final_path = os.path.join(packages_folder, content['name'])
        shutil.copy(package_fpath, final_path)
