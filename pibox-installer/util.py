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
import collections

from path import Path
import humanfriendly

ONE_MiB = 2 ** 20
ONE_GiB = 2 ** 30
ONE_GB = int(1e9)


STAGES = collections.OrderedDict([
    ('master', "Retrieve Master Image"),
    ('download', "Download contents"),
    ('setup', "Image configuration (virtualized)"),
    ('copy', "Copy contents onto image"),
    ('move', "Post-process contents (virtualized)"),
    ('write', "SD-card creation"),
])


class ProgressHelper(object):

    def __init__(self):
        self.stage_id = 'init'
        self.stage_progress = None
        self.will_write = False

    def stage(self, stage_id):
        self.stage_id = stage_id
        self.update()

    def progress(self, percentage=None):
        assert percentage is None or (percentage >= 0 and percentage <= 1)
        self.stage_progress = percentage
        self.update()

    def mark_will_write(self, will_write=True):
        self.will_write = will_write

    @property
    def stage_name(self):
        return STAGES.get(self.stage_id, "Preparations")

    @property
    def nb_of_stages(self):
        n = len(STAGES)
        return n if self.will_write else n - 1

    @property
    def stage_number(self):
        try:
            return list(STAGES.keys()).index(self.stage_id) + 1
        except Exception:
            return 0

    @property
    def stage_numbers(self):
        return "{c}/{t}".format(c=self.stage_number, t=self.nb_of_stages)

    def get_overall_progress(self):
        if not self.stage_number:
            return 0
        span = 1 / self.nb_of_stages
        lbound = span * (self.stage_number - 1)
        if self.stage_progress is None:
            return lbound
        current_progress = self.stage_progress * span
        return lbound + current_progress

    def complete(self):
        raise NotImplementedError()

    def failed(self):
        raise NotImplementedError()

    def update(self):
        raise NotImplementedError()


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

def human_readable_size(size, binary=True):
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
    output = humanfriendly.format_size(num_bytes, binary=binary)
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

class CLILogger(ProgressHelper):
    def __init__(self):
        super(CLILogger, self).__init__()

    def step(self, step):
        if sys.platform == "win32":
            self.p("--> {}".format(step))
        else:
            self.p("\033[00;34m--> " + step + "\033[00m")

    def err(self, err):
        if sys.platform == "win32":
            self.p(err)
        else:
            self.p("\033[00;31m" + err + "\033[00m")

    def raw_std(self, std):
        sys.stdout.write(std)

    def std(self, std, end=None):
        self.p(std, end=end, flush=True)

    def p(self, text, end=None, flush=False):
        print(text, end=end, flush=flush)

    def complete(self):
        self.p("\033[00;32mInstallation succeded.\033[00m")

    def failed(self, error):
        self.err("\033[00;31mInstallation failed: {}\033[00m"
                 .format(error))

    def update(self, step=""):
        self.p("\033[00;35m[STAGE {nums}: {name} - {pc:.0f}%]\033[00m {step}"
               .format(nums=self.stage_numbers,
                       name=self.stage_name,
                       pc=self.get_overall_progress() * 100,
                       step=step))

def get_checksum(fpath, func=hashlib.sha256):
    h = func()
    with open(fpath, "rb") as f:
        for chunk in iter(lambda: f.read(ONE_MiB * 8), b""):
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
