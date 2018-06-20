import os
import re
import threading
import signal
import sys
import base64
import hashlib
import tempfile
import ctypes
import platform
import datetime
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
        self.stage_id = 'init'  # id of current stage
        self.stage_progress = None  # percentage of current stage progress
        self.will_write = False  # wether the process will run write stage

        self.started_on = datetime.datetime.now()  # when the process started
        self.ended_on = None  # when it ended
        self.durations = {}  # records timedeltas for every ran stages

    def start(self, will_write):
        self.started_on = datetime.datetime.now()
        self.will_write = will_write

    def stop(self):
        self.ended_on = datetime.datetime.now()

    def clean_up_stage(self):
        started_on = getattr(self, 'stage_started_on', self.started_on)
        ended_on = datetime.datetime.now()
        self.durations[self.stage_id] = (started_on, ended_on,
                                         ended_on - started_on)
        self.stage_started_on = None
        self.stage_progress = None
        self.tasks = None

    def stage(self, stage_id):
        self.clean_up_stage()  # record duration of previous stage

        self.stage_id = stage_id
        self.stage_started_on = datetime.datetime.now()
        self.update()

    def progress(self, percentage=None):
        assert percentage is None or (percentage >= 0 and percentage <= 1)
        self.stage_progress = percentage
        self.update()

    def ansible(self, line):
        # display output anyway
        self.std(line)

        if self.stage_id not in ['setup', 'move']:
            return

        # detect number of task for ansiblecube phase
        if self.tasks is None and line.startswith("### TASKS ###"):
            try:
                self.tasks = [
                    re.search(r'^\s{6}(.*)\tTAGS\:.*$', l).groups()[0]
                    for l in line.split("^")[5:]]
            except Exception as exp:
                print(str(exp))
                pass

        if self.tasks is not None:
            # detect current task
            if line.startswith("TASK ["):
                try:
                    task = re.search(r'^TASK \[(.*)\] \*+$', line).groups()[0]
                except Exception:
                    return
                else:
                    self.step(task)
                    try:
                        task_index = self.tasks.index(task)
                    except ValueError:
                        pass
                    else:
                        self.progress(task_index / len(self.tasks))

    @property
    def stage_name(self):
        return self.get_stage_name(self.stage_id)

    @property
    def nb_of_stages(self):
        n = len(STAGES)
        return n if self.will_write else n - 1

    @property
    def stage_number(self):
        return self.get_stage_number(self.stage_id)

    @property
    def stage_numbers(self):
        return "{c}/{t}".format(c=self.stage_number, t=self.nb_of_stages)

    def stage_string(self, stage_id):
        return "[{c}/{t}] {n}".format(c=self.get_stage_number(stage_id),
                                      t=self.nb_of_stages,
                                      n=self.get_stage_name(stage_id))

    @classmethod
    def get_stage_number(cls, stage_id):
        try:
            return list(STAGES.keys()).index(stage_id) + 1
        except Exception:
            return 0

    @classmethod
    def get_stage_name(cls, stage_id):
        return STAGES.get(stage_id, "Preparations")

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
        self.clean_up_stage()
        self.stop()

    def failed(self):
        self.clean_up_stage()
        self.stop()

    def update(self):
        raise NotImplementedError()

    def summary(self):
        # make sure we have an end datetime
        if self.ended_on is None:
            self.stop()

        self.std("*** DURATIONS SUMMARY ***")
        for stage_id in STAGES.keys():
            data = self.durations.get(stage_id)
            if data is None:
                continue
            self.std("{stage}: {duration} ({start} to {end})"
                     .format(stage=self.stage_string(stage_id),
                             duration=humanfriendly.format_timespan(
                                 data[2].total_seconds()),
                             start=data[0].strftime('%c'),
                             end=data[1].strftime('%c')))
        duration = self.ended_on - self.started_on
        self.std("TOTAL: {duration} ({start} to {end})"
                 .format(duration=humanfriendly.format_timespan(
                         duration.total_seconds()),
                         start=self.started_on.strftime('%c'),
                         end=self.ended_on.strftime('%c')))

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
        self.p("--> {}".format(step), color="34")

    def err(self, err):
        self.p(err, color="31")

    def raw_std(self, std):
        sys.stdout.write(std)

    def std(self, std, end=None):
        self.p(std, end=end, flush=True)

    def p(self, text, color=None, end=None, flush=False):
        if color is not None and sys.platform != 32:
            text = "\033[00;{col}m{text}\033[00m".format(col=color, text=text)
        print(text, end=end, flush=flush)

    def complete(self):
        super(CLILogger, self).complete()
        self.p("Installation succeded.", color="32")

    def failed(self, error="?"):
        super(CLILogger, self).failed()
        self.err("Installation failed: {}".format(error))

    def update(self):
        self.p("[STAGE {nums}: {name} - {pc:.0f}%]"
               .format(nums=self.stage_numbers,
                       name=self.stage_name,
                       pc=self.get_overall_progress() * 100),
               color="35")

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
    os.makedirs(in_path, exist_ok=True)
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
