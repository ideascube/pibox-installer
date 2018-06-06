import os
import io
import sys
import shutil
import zipfile
import subprocess

import requests

from util import (ReportHook, get_checksum, get_cache)

FAILURE_RETRIES = 3


class RequestedFile(object):
    PENDING = 0
    FAILED = 1
    FOUND = 2
    DOWNLOADED = 3

    def __init__(self, url, fpath):
        self.url = url
        self.fpath = fpath
        self.status = self.PENDING

        self.checksum = None
        self.exception = None
        self.downloaded_size = None

    def set(self, status):
        self.status = status

    @classmethod
    def from_download(cls, url, fpath, downloaded_size):
        rf = cls(url, fpath)
        rf.set(cls.DOWNLOADED)
        rf.downloaded_size = downloaded_size
        return rf

    @classmethod
    def from_disk(cls, url, fpath, checksum):
        rf = cls(url, fpath)
        rf.checksum = checksum
        rf.set(cls.FOUND)
        return rf

    @classmethod
    def from_failure(cls, url, fpath, exception, checksum=None):
        rf = cls(url, fpath)
        rf.set(cls.FAILED)
        rf.exception = exception
        rf.checksum = checksum
        return rf

    @property
    def successful(self):
        return self.status in (self.DOWNLOADED, self.FOUND)

    @property
    def found(self):
        return self.status == self.FOUND

    @property
    def downloaded(self):
        return self.status == self.DOWNLOADED

    @property
    def present(self):
        return os.path.exists(self.fpath)

    @property
    def verified(self):
        return self.present and get_checksum(self.fpath) == self.checksum


def stream(url, write_to=None, callback=None, block_size=1024):
    # prepare adapter so it retries on failure
    session = requests.Session()
    # retries up-to FAILURE_RETRIES whichever kind of listed error
    retries = requests.packages.urllib3.util.retry.Retry(
        total=FAILURE_RETRIES,  # total number of retries
        connect=FAILURE_RETRIES,  # connection errors
        read=FAILURE_RETRIES,  # read errors
        status=2,  # failure HTTP status (only those bellow)
        redirect=False,  # don't fail on redirections
        backoff_factor=1,  # sleep factor between retries
        status_forcelist=[413, 429, 500, 502, 503, 504])
    retry_adapter = requests.adapters.HTTPAdapter(max_retries=retries)
    session.mount('http', retry_adapter)
    req = session.get(url, stream=True)

    total_size = int(req.headers.get('content-length', 0))
    total_downloaded = 0
    if write_to is not None:
        fd = open(write_to, 'wb')
    else:
        fd = io.BytesIO()

    for data in req.iter_content(block_size):
        callback(data, block_size, total_size)
        total_downloaded += len(data)
        if write_to:
            fd.write(data)

    if write_to:
        fd.close()
    else:
        fd.seek(0)

    if total_size != 0 and total_downloaded != total_size:
        raise AssertionError("Downloaded size is different than expected")

    return total_downloaded, write_to if write_to else fd


def download_file(url, fpath, logger, checksum=None):
    hook = ReportHook(logger.raw_std).reporthook
    try:
        size, path = stream(url, fpath, callback=hook)
    except Exception as exp:
        return RequestedFile.from_failure(url, fpath, exp, checksum)

    return RequestedFile.from_download(url, fpath, size)


def download_if_missing(url, fpath, logger, checksum=None):
    # file already downloaded
    if checksum and os.path.exists(fpath):
        logger.std("calculating sum for {}...".format(fpath), '')
        if get_checksum(fpath) == checksum:
            logger.std("MATCH.")
            return RequestedFile.from_disk(url, fpath, checksum)
        logger.std("MISMATCH.")

    return download_file(url, fpath, logger, checksum)


def get_content_cache(content, folder, is_cache_folder=False):
    ''' shortcut to content's fpath from build_folder or cache_folder '''
    cache_folder = folder if is_cache_folder else get_cache(folder)
    return os.path.join(cache_folder, content.get('name'))


def download_content(content, logger, build_folder):
    return download_if_missing(url=content.get('url'),
                               fpath=get_content_cache(content, build_folder),
                               logger=logger,
                               checksum=content.get('checksum'))


def unzip_file(archive_fpath, src_fname, build_folder, dest_fpath=None):
    with zipfile.ZipFile(archive_fpath, 'r') as zip_archive:
        extraction = zip_archive.extract(src_fname, build_folder)
        if dest_fpath:
            shutil.move(extraction, dest_fpath)


def unzip_archive(archive_fpath, dest_folder):
    with zipfile.ZipFile(archive_fpath) as zip_archive:
        zip_archive.extractall(dest_folder)


def unarchive(archive_fpath, dest_folder):
    ''' single poe for extracting our content archives '''
    supported_extensions = ('.tar', '.tar.bz2', '.tar.gz', '.zip')
    if sum([1 for ext in supported_extensions
            if archive_fpath.endswith(ext)]) == 0:
        raise NotImplementedError("Archive format extraction not supported: {}"
                                  .format(archive_fpath))

    if archive_fpath.endswith('.zip'):
        unzip_archive(archive_fpath, dest_folder)
        return

    if sys.platform == 'win32':
        bin_path = sys._MEIPASS if getattr(sys, "frozen", False) else "."
        szip_exe = os.path.join(bin_path, '7za.exe')
        command = [szip_exe, 'x', '-o', dest_folder, archive_fpath]
    else:
        command = ['tar', '-C', dest_folder, '-x', '-f', archive_fpath]

    subprocess.check_call(command)
