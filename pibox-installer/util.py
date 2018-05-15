import os
import threading
import signal
import sys
import base64
import hashlib
import tempfile
import ctypes
import platform
import data

from path import Path
import humanfriendly

ONE_MB = 2 ** 20
ONE_GB = 2 ** 30

def compute_space_required(catalog, zim_list, kalite, wikifundi, aflatoun, edupi):
    # TODO: compute actual space used with empty install
    used_space = 2 * 2**30 # space of raspbian with ideascube without content
    if zim_list:
        zim_space_required = {}
        for one_catalog in catalog:
            for (key, value) in one_catalog["all"].items():
                if zim_space_required.get(key):
                    raise ValueError("same key in two catalogs")
                zim_space_required[key] = value["size"]*2

        for zim in zim_list:
            used_space += zim_space_required[zim]
    if kalite:
        for lang in kalite:
            used_space += data.kalite_sizes[lang]
    if wikifundi:
        for lang in wikifundi:
            used_space += data.wikifundi_sizes[lang]
    if aflatoun:
        used_space += data.aflatoun_size
    if edupi:
        used_space += data.edupi_size

    return used_space

def get_free_space_in_dir(dirname):
    """Return folder/drive free space."""
    if platform.system() == 'Windows':
        free_bytes = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(dirname), None, None, ctypes.pointer(free_bytes))
        return free_bytes.value
    else:
        st = os.statvfs(dirname)
        return st.f_bavail * st.f_frsize

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

def human_readable_size(size):
    if isinstance(size, (int, float)):
        num_bytes = size
    else:
        try:
            num_bytes = humanfriendly.parse_size(size)
        except Exception:
            return "NaN"
    is_neg = num_bytes < 0
    if is_neg:
        num_bytes = abs(num_bytes)
    output = humanfriendly.format_size(num_bytes, binary=True)
    if is_neg:
        return "- {}".format(output)
    return output

class ReportHook():
    def __init__(self, writter):
        self._current_size = 0
        self.width = 60
        self._last_line = None
        self._writter = writter
        self.reporthook(0, 0, 100)  # display empty bar as we start

    def reporthook(self, chunk, chunk_size, total_size):
        if chunk != 0:
            self._current_size += chunk_size

        avail_dots = self.width-2
        if total_size == -1:
            line = "unknown size"
        elif self._current_size >= total_size:
            line = "[" + "."*avail_dots + "] 100%\n"
        else:
            ratio = min(float(self._current_size) / total_size, 1.)
            shaded_dots = min(int( ratio * avail_dots), avail_dots)
            percent = min(int(ratio*100), 100)
            line = "[" + "."*shaded_dots + " "*(avail_dots-shaded_dots) + "] " + str(percent) + "%\r"

        if line != self._last_line:
            self._last_line = line
            self._writter(line)

class CLILogger:
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
    def std(cls, std, end=None):
        print(std, end=end, flush=True)

def get_checksum(fpath, func=hashlib.sha256):
    h = func()
    with open(fpath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()

def get_cache(build_folder):
    fpath = os.path.join(build_folder, "cache")
    os.makedirs(fpath, exist_ok=True)
    return fpath

def get_temp_folder(in_path):
    return tempfile.mkdtemp(dir=in_path)

def relpathto(dest):
    ''' relative path to an absolute one '''
    if dest is None:
        return None
    return str(Path(dest).relpath())

def b64encode(fpath):
    ''' base64 string of a binary file '''
    with open(fpath, "rb") as fp:
        return base64.b64encode(fp.read()).decode('utf-8')

def b64decode(fname, data, to):
    ''' write back a binary file from its fname and base64 string '''
    fpath = os.path.join(to, fname)
    with open(fpath, 'wb') as fp:
        fp.write(base64.b64decode(data))
    return fpath
