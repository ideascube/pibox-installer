#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import re
import json
import math
import shutil
import itertools

from data import content_file, mirror
from util import get_temp_folder, get_checksum, ONE_GiB
from backend.catalog import YAML_CATALOGS
from backend.download import get_content_cache, unarchive

# prepare CONTENTS from JSON file
with open(content_file, 'r') as fp:
    CONTENTS = json.load(fp)
    for key, dl_data in CONTENTS.items():
        if 'url' in dl_data.keys():
            CONTENTS[key]['url'] = CONTENTS[key]['url'].format(mirror=mirror)


def get_content(key):
    if key not in CONTENTS:
        raise KeyError("requested content `{}` is not in CONTENTS".format(key))
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


def get_all_contents_for(collection):
    ''' flat list of contents for the collection '''
    return itertools.chain.from_iterable([
        content_dl_cb(**cb_kwargs)
        for _, content_dl_cb, _, cb_kwargs
        in collection
    ])


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
    ''' aflatoun: single large tarball with content + mini lang packs '''
    return [get_content('aflatoun_content')] + [
        get_content('aflatoun_langpack_{lang}'.format(lang=lang))
        for lang in languages]


def get_package_content(package_id):
    for catalog in YAML_CATALOGS:
        try:
            package = catalog['all'][package_id]
            return {
                "url": package['url'],
                "name": "package_{langid}-{version}".format(**package),
                "checksum": package['sha256sum'],
                "archive_size": package['size'],
                "expanded_size": package['size'] * 1
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


def move(content, cache_folder, final_path):
    # retrieve archive path
    archive_fpath = get_content_cache(content, cache_folder, True)

    # move useful content to final path
    shutil.move(archive_fpath, final_path)


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
        move(content=lang_pack,
             cache_folder=cache_folder,
             final_path=os.path.join(mount_point, lang_pack['name']))

        # videos
        videos = get_content('kalite_videos_{lang}'.format(lang=lang))
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
        lang_key = 'wikifundi_langpack_{lang}'.format(lang=lang)
        content = get_content(lang_key)
        extract_and_move(
            content=content,
            cache_folder=cache_folder,
            root_path=mount_point,
            final_path=os.path.join(mount_point, lang_key))


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
    packages_folder = os.path.join(mount_point, "packages_cache")
    os.makedirs(packages_folder, exist_ok=True)

    for package in packages:
        content = get_package_content(package)
        logger.std("Copying {p} to {f}".format(p=content['name'],
                                               f=packages_folder))

        # retrieve downloaded path
        package_fpath = get_content_cache(content, cache_folder, True)
        # copy to the packages folder
        final_path = os.path.join(packages_folder,
                                  re.sub(r'^package_', '', content['name']))
        shutil.copy(package_fpath, final_path)


def content_is_cached(content, cache_folder, check_sum=False):
    ''' whether a content is already present in cache '''
    content_fpath = os.path.join(cache_folder, content.get('name'))
    if not os.path.exists(content_fpath) \
            or os.path.getsize(content_fpath) != content.get('archive_size'):
        return False

    if check_sum:
        return get_checksum(content_fpath) == content.get('checksum')

    return True


def get_collection_download_size(collection):
    ''' data usage to download all of the collection '''
    return sum([item.get('archive_size')
                for item in get_all_contents_for(collection)])


def get_collection_download_size_using_cache(collection, cache_folder):
    ''' data usage to download missing elements of the collection '''
    return sum([item.get('archive_size')
                for item in get_all_contents_for(collection)
                if not content_is_cached(item, cache_folder)])


def get_expanded_size(collection):
    ''' sum of extracted sizes of all collection with 10%|2GB margin '''
    total_size = sum([item.get('expanded_size') * 2
                      if item.get('copied_on_destination', False)
                      else item.get('expanded_size')
                      for item in get_all_contents_for(collection)])
    margin = min([2 * ONE_GiB, total_size * 0.1])
    return total_size + margin


def get_required_image_size(collection):
    required_size = sum([
        get_content('pibox_base_image').get('root_partition_size'),
        get_expanded_size(collection)])

    # round it up to next GiB
    return math.ceil(required_size / ONE_GiB) * ONE_GiB


def get_required_building_space(collection, cache_folder, image_size=None):
    ''' total required space to host downlaods and image '''
    # the pibox master image
    # we neglect the master's expanded size as it is going to be moved
    # to the image path and resized in-place (never reduced)
    base_image_size = get_content('pibox_base_image').get('archive_size')

    # the created image
    if image_size is None:
        image_size = get_required_image_size(collection)

    # download cache
    downloads_size = get_collection_download_size_using_cache(
        collection, cache_folder)

    total_size = sum([base_image_size, image_size, downloads_size])

    margin = min([2 * ONE_GiB, total_size * 0.2])
    return total_size + margin
