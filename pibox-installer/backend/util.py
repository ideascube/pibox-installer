import os
import sys
import ctypes
import random
import threading
import subprocess

from util import CLILogger, ONE_MiB, human_readable_size


# windows-only flags to prevent sleep on executing thread
WINDOWS_SLEEP_FLAGS = {
    # Enables away mode. This value must be specified with ES_CONTINUOUS.
    # Away mode should be used only by media-recording and media-distribution
    # applications that must perform critical background processing
    # on desktop computers while the computer appears to be sleeping.
    'ES_AWAYMODE_REQUIRED': 0x00000040,
    # Informs the system that the state being set should remain in effect until
    # the next call that uses ES_CONTINUOUS and one of the other state flags is cleared.
    'ES_CONTINUOUS': 0x80000000,
    # Forces the display to be on by resetting the display idle timer.
    'ES_DISPLAY_REQUIRED': 0x00000002,
    # Forces the system to be in the working state by resetting the system idle timer.
    'ES_SYSTEM_REQUIRED': 0x00000001,
}


class CheckCallException(Exception):
    def __init__(self, msg):
        Exception(self, msg)


def startup_info_args():
    if hasattr(subprocess, 'STARTUPINFO'):
        # On Windows, subprocess calls will pop up a command window by default
        # when run from Pyinstaller with the ``--noconsole`` option. Avoid this
        # distraction.
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    else:
        si = None
    return {'startupinfo': si}


def subprocess_pretty_call(cmd, logger, stdin=None,
                           check=False, decode=False, as_admin=False):
    ''' flexible subprocess helper running separately and using the logger

        cmd: the command to be run
        logger: the logger to send debug output to
        stdin: pipe input into the command
        check: whether it should raise on non-zero return code
        decode: whether it should decode output (bytes) into UTF-8 str
        as_admin: whether the command should be run as root/admin '''

    if as_admin:
        if sys.platform == "win32":
            if logger is not None:
                logger.std("Call (as admin): " + str(cmd))
            return run_as_win_admin(cmd, logger)

        from_cli = logger is None or type(logger) == CLILogger
        cmd = get_admin_command(cmd, from_gui=not from_cli)

    # We should use subprocess.run but it is not available in python3.4
    process = subprocess.Popen(cmd, stdin=stdin,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, **startup_info_args())

    if logger is not None:
        logger.std("Call: " + str(process.args))

    process.wait()

    lines = [l.decode('utf-8', 'ignore')
             for l in process.stdout.readlines()] \
        if decode else process.stdout.readlines()

    if logger is not None:
        for line in lines:
            logger.raw_std(line if decode else line.decode("utf-8", "ignore"))

    if check:
        if process.returncode != 0:
            raise CheckCallException("Process {} failed with: {}"
                                     .format(process.args, process.returncode))
        return lines

    return process.returncode, lines


def subprocess_pretty_check_call(cmd, logger, stdin=None, as_admin=False):
    return subprocess_pretty_call(cmd=cmd, logger=logger,
                                  stdin=stdin, check=True, as_admin=as_admin)


def subprocess_external(cmd, logger):
    ''' spawn a new process without capturing nor watching it '''
    logger.std("Opening: " + str(cmd))
    subprocess.Popen(cmd)


def is_admin():
    ''' whether current process is ran as Windows Admin or unix root '''
    if sys.platform == "win32":
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False
    return os.getuid() == 0


def run_as_win_admin(command, logger):
    ''' run specified command with admin rights '''
    params = " ".join(['"{}"'.format(x) for x in command[1:]]).strip()
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas",
                                             command[0],
                                             params, None, 1)
    # ShellExecuteW returns 5 if user chose not to elevate
    if rc == 5:
        raise PermissionError()
    return rc


def get_admin_command(command, from_gui):
    ''' updated command to run it as root on macos or linux

        from_gui: whether called via GUI. Using cli sudo if not '''

    if not from_gui:
        return ["sudo"] + command

    if sys.platform == "darwin":
        return ['/usr/bin/osascript', '-e',
                "do shell script \"{command} 2>&1\" "
                "with administrator privileges"
                .format(command=" ".join(command))]
    if sys.platform == "linux":
        return ["pkexec"] + command


def open_handles(image_fpath, device_fpath, read_only=False):
    img_flag = os.O_RDONLY
    dev_flag = os.O_RDONLY if read_only else os.O_WRONLY
    if os.name == "posix":
        return (os.open(image_fpath, img_flag),
                os.open(device_fpath, dev_flag))
    elif os.name == "nt":
        dev_flag = dev_flag | os.O_BINARY
        return (os.open(image_fpath, img_flag),
                os.open(device_fpath, dev_flag))
    else:
        raise NotImplementedError("Platform not supported")


def close_handles(image_fd, device_fd):
    try:
        os.close(image_fd)
        os.close(device_fd)
    except Exception:
        pass


def ensure_card_written(image_fpath, device_fpath, logger):
    ''' asserts image and device content is same (reads rand 4MiB from both '''

    logger.step("Verify data on SD card")

    image_fd, device_fd = open_handles(image_fpath, device_fpath, read_only=True)

    # read a 4MiB random part from the image
    buffer_size = 4 * ONE_MiB
    total_size = os.lseek(image_fd, 0, os.SEEK_END)
    offset = random.randint(0, int((total_size - buffer_size) * .8))
    offset -= (offset % 512)
    logger.std("reading {n}b from offset {s} out of {t}b."
               .format(n=buffer_size, s=offset, t=total_size))

    try:
        # read same part from the SD card and compare
        os.lseek(image_fd, offset, os.SEEK_SET)
        os.lseek(device_fd, offset, os.SEEK_SET)
        if not os.read(image_fd, buffer_size) == os.read(device_fd, buffer_size):
            raise ValueError("Image and SD-card challenge do not match.")
    except Exception:
        raise
    finally:
        close_handles(image_fd, device_fd)


class ImageWriterThread(threading.Thread):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._should_stop = False  # stop flag
        self.exp = None  # exception to be re-raised by caller

    def stop(self):
        self._should_stop = True

    def run(self):
        image_fpath, device_fpath, logger = self._args

        logger.step("Copy image to sd card")

        image_fd, device_fd = open_handles(image_fpath, device_fpath)

        total_size = os.lseek(image_fd, 0, os.SEEK_END)
        os.lseek(image_fd, 0, os.SEEK_SET)

        if os.name == "nt":
            buffer_size = 512  # safer on windows
            logger_break = 1000
        else:
            buffer_size = 25 * ONE_MiB
            logger_break = 4
        steps = total_size // buffer_size

        for step in range(0, steps):

            if self._should_stop:
                break

            # only update logger every 4 steps (100MiB)
            if step % logger_break == 0:
                logger.progress(step, steps)
                logger.std(
                    "Copied {copied} of {total} ({pc:.2f}%)"
                    .format(copied=human_readable_size(step * buffer_size),
                            total=human_readable_size(total_size),
                            pc=step / steps * 100))

            try:
                os.write(device_fd, os.read(image_fd, buffer_size))
            except Exception as exp:
                logger.std("Exception during write: {}".format(exp))
                close_handles(image_fd, device_fd)
                self.exp = exp
                raise

        if not self._should_stop and total_size % buffer_size:
            logger.std("Writing last chunk...")
            try:
                os.write(device_fd, os.read(image_fd, total_size % buffer_size))
            except Exception as exp:
                logger.std("Exception during write: {}".format(exp))
                close_handles(image_fd, device_fd)
                self.exp = exp
                raise

        logger.progress(1)
        logger.step("sync")
        if not self._should_stop:
            os.fsync(device_fd)
        close_handles(image_fd, device_fd)


def prevent_sleep(logger):
    if sys.platform == "win32":
        logger.std("Setting ES_SYSTEM_REQUIRED mode to current thread")
        ctypes.windll.kernel32.SetThreadExecutionState(
            WINDOWS_SLEEP_FLAGS['ES_CONTINUOUS'] |
            WINDOWS_SLEEP_FLAGS['ES_SYSTEM_REQUIRED'] |
            WINDOWS_SLEEP_FLAGS['ES_DISPLAY_REQUIRED'])
        return

    if sys.platform == "linux":
        def make_unmapped_window(wm_name):
            from Xlib import display
            screen = display.Display().screen()
            window = screen.root.create_window(0, 0, 1, 1, 0, screen.root_depth)
            window.set_wm_name(wm_name)
            window.set_wm_protocols([])
            return window

        logger.std("Suspending xdg-screensaver")
        wid = None
        try:
            # Create window to use with xdg-screensaver
            window = make_unmapped_window("caffeinate")
            wid = hex(window.id)

            logger.std("{}".format(os.environ))

            cmd = ['/usr/bin/xdg-screensaver', 'suspend', wid]
            logger.std("Calling {}".format(cmd))
            p = subprocess.Popen(" ".join(cmd),
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 shell=True)
            out, errs = p.communicate(timeout=5)
            logger.std("returncode: {}".format(p.returncode))
            logger.std("output: ".format(
                out if out is None else out.decode('utf-8', 'ignore')))
            logger.std("errors: ".format(
                errs if errs is None else errs.decode('utf-8', 'ignore')))
            # subprocess_pretty_check_call(cmd, logger)
        except Exception as exp:
            logger.err("Unable to prevent sleep...")
            raise
        return wid

    if sys.platform == "darwin":
        cmd = ["/usr/bin/caffeinate", "-dsi"]
        logger.std("Calling {}".format(cmd))
        process = subprocess.Popen(cmd, **startup_info_args())

        return process

def restore_sleep_policy(reference, logger):
    if sys.platform == "win32":
        logger.std("Restoring ES_CONTINUOUS mode to current thread")
        ctypes.windll.kernel32.SetThreadExecutionState(
            WINDOWS_SLEEP_FLAGS['ES_CONTINUOUS'])
        return

    if sys.platform == "linux":
        logger.std("Resuming xdg-screensaver (wid #{})".format(reference))
        if reference is not None:
            subprocess_pretty_call(
                ['/usr/bin/xdg-screensaver', 'resume', reference], logger)
        return

    if sys.platform == "darwin":
        logger.std("Stopping caffeinate process #{}".format(reference.pid))
        reference.kill()
        reference.wait(5)
        return
