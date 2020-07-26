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

    def test_check_permission(self):
        aud = auditor.Auditor()
        aud.permission_read_paths.append('/test/root/src/permit_read')
        aud.permission_write_paths.append('/test/root/src/permit_write')
        self.assertFalse(aud.ask_readable('/test/root/src/forbid_read/file1'))
        self.assertFalse(aud.ask_writable('/test/root/src/forbid_write/file1'))
        self.assertFalse(aud.ask_readable('/test/root/src/forbid_read/nest1/file1'))
        self.assertFalse(aud.ask_writable('/test/root/src/forbid_write/nest1/file1'))
        self.assertTrue(aud.ask_readable('/test/root/src/permit_read'))
        self.assertTrue(aud.ask_writable('/test/root/src/permit_write'))
        self.assertTrue(aud.ask_readable('/test/root/src/permit_read/file1'))
        self.assertTrue(aud.ask_writable('/test/root/src/permit_write/file1'))
        self.assertTrue(aud.ask_readable('/test/root/src/permit_read/nest1/file1'))
        self.assertTrue(aud.ask_writable('/test/root/src/permit_write/nest1/file1'))
