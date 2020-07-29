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

    def test_check_permission_basic(self):
        aud = auditor.Auditor()
        aud.allowread('/test/root/src/permit_read')
        aud.allowwrite('/test/root/src/permit_write')
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

    def test_check_permission_order(self):
        aud = auditor.Auditor()
        self.assertFalse(aud.ask_readable('/test/root/sample1'))
        aud.allowread('/test/root/sample1')
        self.assertTrue(aud.ask_readable('/test/root/sample1'))
        aud.denyread('/test/root/sample1')
        self.assertFalse(aud.ask_readable('/test/root/sample1'))

        self.assertFalse(aud.ask_writable('/test/root/sample1'))
        aud.allowwrite('/test/root/sample1')
        self.assertTrue(aud.ask_writable('/test/root/sample1'))
        aud.denywrite('/test/root/sample1')
        self.assertFalse(aud.ask_writable('/test/root/sample1'))

    def test_check_permission_hierarchy(self):
        aud = auditor.Auditor()
        self.assertFalse(aud.ask_readable('/test/root/a/b/c'))
        aud.allowread('/test/root/a')
        self.assertTrue(aud.ask_readable('/test/root/a/b/c'))
        aud.denyread('/test/root/a/b')
        self.assertFalse(aud.ask_readable('/test/root/a/b/c'))
        aud.allowread('/test/root/a')
        self.assertTrue(aud.ask_readable('/test/root/a/b/c'))
        aud.denyread('/test/root/a/b')
        self.assertFalse(aud.ask_readable('/test/root/a/b/c'))

    def test_check_permission_spec(self):
        aud = auditor.Auditor()

        self.assertFalse(aud.ask_readable('/foo'))
        self.assertFalse(aud.ask_writable('/foo'))

        aud.denyread('/foo'); aud.denywrite('/foo')  # same as adddeny
        self.assertFalse(aud.ask_readable('/foo'))
        self.assertFalse(aud.ask_writable('/foo'))

        aud.allowread('/foo/bar'); aud.allowwrite('/foo/bar')  # same as addwrite
        self.assertTrue(aud.ask_readable('/foo/bar'))
        self.assertTrue(aud.ask_writable('/foo/bar'))

        aud.denyread('/foo/bar/baz'); aud.denywrite('/foo/bar/baz')  # same as adddeny
        self.assertFalse(aud.ask_readable('/foo/bar/baz'))
        self.assertFalse(aud.ask_writable('/foo/bar/baz'))

        aud.allowread('/foo/bar/baz')  # same as addread
        self.assertTrue(aud.ask_readable('/foo/bar/baz'))
        self.assertFalse(aud.ask_writable('/foo/bar/baz'))
