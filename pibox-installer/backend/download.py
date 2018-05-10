import os
import io
import requests

from util import ReportHook, get_md5


class RequestedFile(object):
    PENDING = 0
    FAILED = 1
    FOUND = 2
    DOWNLOADED = 3

    def __init__(self, url, fpath):
        self.url = url
        self.fpath = fpath
        self.status = self.PENDING

        self.md5_sum = None
        self.exception = None
        self.downloaded_size = None

    def set(self, status):
        self.status = status

    @classmethod
    def from_download(cls, url, fpath):
        rf = cls(url, fpath)
        rf.set(cls.DOWNLOADED)
        return rf

    @classmethod
    def from_disk(cls, url, fpath, md5_sum):
        rf = cls(url, fpath)
        rf.md5_sum = md5_sum
        rf.set(cls.FOUND)
        return rf

    @classmethod
    def from_failure(cls, url, fpath, exception, md5_sum=None):
        rf = cls(url, fpath)
        rf.set(cls.FAILED)
        rf.exception = exception
        rf.md5_sum = md5_sum
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
        return self.present and get_md5(self.fpath) == self.md5_sum


def stream(url, write_to=None, callback=None, block_size=1024):
    req = requests.get(url, stream=True)
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


def download_file(url, fpath, logger, md5_sum=None):
    hook = ReportHook(logger.raw_std).reporthook
    try:
        size, path = stream(url, fpath, callback=hook)
    except Exception as exp:
        return RequestedFile.from_failure(url, fpath, exp, md5_sum)

    return RequestedFile.from_download(url, fpath)


def download_if_missing(url, fpath, logger, md5_sum):
    # file already downloaded
    if os.path.exists(fpath) and get_md5(fpath) == md5_sum:
        return RequestedFile.from_disk(url, fpath, md5_sum)

    return download_file(url, fpath, logger, md5_sum)
