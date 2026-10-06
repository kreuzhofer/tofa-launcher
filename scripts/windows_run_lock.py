"""Kernel-held invocation lease; a recorded PID alone does not prove liveness."""
import fcntl
import os
import stat

from windows_template_transport import Failure


class InvocationLease:
    def __init__(self, root):
        self.descriptor = os.open(root / 'invocation.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(self.descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077 or info.st_nlink != 1):
                raise Failure('unsafe_invocation_lease')
            self.identity = {'device': info.st_dev, 'inode': info.st_ino}
            try:
                fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.held = True
            except BlockingIOError:
                self.held = False
        except BaseException:
            os.close(self.descriptor)
            raise

    def close(self):
        os.close(self.descriptor)
