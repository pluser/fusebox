import typing as typ
import unittest
import functools
from unittest.mock import MagicMock, patch
import trio
from fusebox import fusefs
from fusebox import auditor
import pyfuse3


class TestAuditor(unittest.TestCase):

    @staticmethod
    def _exec(func, *args, **kwargs):
        return trio.run(functools.partial(func, *args, **kwargs))

    @patch('fusebox.fusefs.os.path.isdir')
    @patch('fusebox.fusefs.os.path.exists')
    @patch('fusebox.fusefs.os.lstat')
    def test_getatter(self, *_):
        fsops = fusefs.Fusebox('/test/root/src', '/test/root/dst')
        aud = auditor.Auditor()
        fsops.register_auditor(aud)
        fsops.dispatch_auditor('getattr', 1234, None)

    def test_check_permission(self):
        aud = auditor.Auditor()
        aud.add_read_forbidden_path('/test/root/src/forbid_read')
        aud.add_write_forbidden_path('/test/root/src/forbid_write')
        self.assertFalse(aud.readable('/test/root/src/forbid_read/file1'))
        self.assertFalse(aud.writable('/test/root/src/forbid_write/file1'))
