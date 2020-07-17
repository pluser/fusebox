import os
import errno
import trio
import pyfuse3
import functools
from collections import UserDict
import stat
import unittest
from unittest.mock import MagicMock, patch
from fusebox import fusefs


class TestFuseFS(unittest.TestCase):
    PATH_SRC = '/test/root/path'
    PATH_DST = '/test/root/path/dest'

    @staticmethod
    def _exec(func, *args, **kwargs):
        return trio.run(functools.partial(func, *args, **kwargs))

    def setUp(self):
        self.patch_os_path_exists = patch('fusebox.fusefs.os.path.exists')
        self.mock_os_path_exists = self.patch_os_path_exists.start()
        self.mock_os_path_exists.return_value = True

    def tearDown(self):
        self.patch_os_path_exists.stop()

    @patch('fusebox.fusefs.os.lstat')
    @patch('fusebox.fusefs.os.path.isdir')
    def test_init(self, mock_isdir, mock_lstat):
        mock_isdir.return_value = True
        ops = fusefs.Fusebox(self.PATH_SRC, self.PATH_DST)
        return ops

    @patch('fusebox.fusefs.pyfuse3.EntryAttributes')
    def test__getattr(self, mock_entatt):
        ops = self.test_init()
        vinfo_a = ops.vm.create_vinfo()
        vinfo_a.add_path('/test/root/file1')
        vinfo_mp = ops.vm.create_vinfo()
        vinfo_mp.add_path(self.PATH_DST)
        self.assertRaises(pyfuse3.FUSEError, ops._getattr, vinfo_mp)
        with patch('fusebox.fusefs.os.lstat') as mock_lstat:
            mock_lstat.side_effect = OSError(errno.ENOENT, 'Artifact Error')
            self.assertRaises(pyfuse3.FUSEError, ops._getattr, vinfo_a)
        with patch('fusebox.fusefs.os.lstat') as mock_lstat:
            entry = ops._getattr(vinfo_a)
            mock_lstat.assert_called_once_with(vinfo_a.path)
            self.assertEqual(entry.st_ino, vinfo_a.vnode)

    class DefaultAttrDict(UserDict):
        def __init__(self, default, **kwargs):
            super().__init__(kwargs)
            self.defaultvalue = default

        def __getattr__(self, name):
            return self.data[name] if name in self.data else self.defaultvalue

    @patch('fusebox.fusefs.os.lstat')
    def setup_setattr(self, *_):
        ops = self.test_init()
        vinfo = ops.vm.create_vinfo()
        vinfo.add_path(self.PATH_SRC + '/file1')
        vinfo.open_vnode(7)
        return ops, vinfo

    @patch('fusebox.fusefs.os.lstat')
    @patch('fusebox.fusefs.os.truncate')
    def test_setattr_size_path(self, mock_trunc, *_):
        ops, vinfo = self.setup_setattr()
        attr = MagicMock()
        needs = self.DefaultAttrDict(default=False, update_size=True)
        self._exec(ops.setattr, vinfo.vnode, attr, needs, None, None)
        mock_trunc.assert_called_once_with(
            vinfo.path,
            attr.st_size
        )

    @patch('fusebox.fusefs.os.lstat')
    @patch('fusebox.fusefs.os.fstat')
    @patch('fusebox.fusefs.os.ftruncate')
    def test_setattr_size_fd(self, mock_trunc, *_):
        ops, vinfo = self.setup_setattr()
        attr = MagicMock()
        needs = self.DefaultAttrDict(default=False, update_size=True)
        self._exec(ops.setattr, None, attr, needs, next(iter(vinfo.fds)), None)
        mock_trunc.assert_called_once_with(
            next(iter(vinfo.fds)),
            attr.st_size
        )

    @patch('fusebox.fusefs.os.lstat')
    @patch('fusebox.fusefs.stat.S_IMODE')
    @patch('fusebox.fusefs.os.chmod')
    def test_setattr_mode_path(self, mock_chmod, *_):
        ops, vinfo = self.setup_setattr()
        attr = MagicMock()
        needs = self.DefaultAttrDict(default=False, update_mode=True)
        self._exec(ops.setattr, vinfo.vnode, attr, needs, None, None)
        mock_chmod.assert_called_once_with(
            vinfo.path,
            stat.S_IMODE(attr.st_mode)
        )

    @patch('fusebox.fusefs.os.lstat')
    @patch('fusebox.fusefs.os.fstat')
    @patch('fusebox.fusefs.stat.S_IMODE')
    @patch('fusebox.fusefs.os.fchmod')
    def test_setattr_mode_fd(self, mock_chmod, *_):
        ops, vinfo = self.setup_setattr()
        attr = MagicMock()
        needs = self.DefaultAttrDict(default=False, update_mode=True)
        self._exec(ops.setattr, None, attr, needs, next(iter(vinfo.fds)), None)
        mock_chmod.assert_called_once_with(
            next(iter(vinfo.fds)),
            stat.S_IMODE(attr.st_mode)
        )

    @patch('fusebox.fusefs.os.lstat')
    @patch('fusebox.fusefs.os.chown')
    def test_setattr_chuid_path(self, mock_chown, *_):
        ops, vinfo = self.setup_setattr()
        attr = MagicMock()
        needs = self.DefaultAttrDict(default=False, update_uid=True)
        self._exec(ops.setattr, vinfo.vnode, attr, needs, None, None)
        mock_chown.assert_called_once_with(
            vinfo.path,
            attr.st_uid,
            -1,
            follow_symlinks=False
        )

    @patch('fusebox.fusefs.os.lstat')
    @patch('fusebox.fusefs.os.fstat')
    @patch('fusebox.fusefs.os.fchown')
    def test_setattr_chuid_fd(self, mock_chown, *_):
        ops, vinfo = self.setup_setattr()
        attr = MagicMock()
        needs = self.DefaultAttrDict(default=False, update_uid=True)
        self._exec(ops.setattr, None, attr, needs, next(iter(vinfo.fds)), None)
        mock_chown.assert_called_once_with(
            next(iter(vinfo.fds)),
            attr.st_uid,
            -1,
            follow_symlinks=False
        )

    @patch('fusebox.fusefs.os.lstat')
    @patch('fusebox.fusefs.os.chown')
    def test_setattr_chgid_path(self, mock_chown, *_):
        ops, vinfo = self.setup_setattr()
        attr = MagicMock()
        needs = self.DefaultAttrDict(default=False, update_gid=True)
        self._exec(ops.setattr, vinfo.vnode, attr, needs, None, None)
        mock_chown.assert_called_once_with(
            vinfo.path,
            -1,
            attr.st_gid,
            follow_symlinks=False
        )

    @patch('fusebox.fusefs.os.lstat')
    @patch('fusebox.fusefs.os.fstat')
    @patch('fusebox.fusefs.os.fchown')
    def test_setattr_chgid_fd(self, mock_chown, *_):
        ops, vinfo = self.setup_setattr()
        attr = MagicMock()
        needs = self.DefaultAttrDict(default=False, update_gid=True)
        self._exec(ops.setattr, None, attr, needs, next(iter(vinfo.fds)), None)
        mock_chown.assert_called_once_with(
            next(iter(vinfo.fds)),
            -1,
            attr.st_gid,
            follow_symlinks=False
        )

    @patch('fusebox.fusefs.os.lstat')
    @patch('fusebox.fusefs.os.utime')
    def test_setattr_atime_path(self, mock_utime, *_):
        ops, vinfo = self.setup_setattr()
        attr = MagicMock()
        needs = self.DefaultAttrDict(default=False, update_atime=True)
        self._exec(ops.setattr, vinfo.vnode, attr, needs, None, None)
        mock_utime.assert_called_once_with(
            vinfo.path,
            None,
            ns=(attr.st_atime_ns, os.lstat(vinfo.path).st_mtime_ns),
            follow_symlinks=False)

    @patch('fusebox.fusefs.os.lstat')
    @patch('fusebox.fusefs.os.fstat')
    @patch('fusebox.fusefs.os.utime')
    def test_setattr_atime_fd(self, mock_utime, *_):
        ops, vinfo = self.setup_setattr()
        attr = MagicMock()
        needs = self.DefaultAttrDict(default=False, update_atime=True)
        self._exec(ops.setattr, None, attr, needs, next(iter(vinfo.fds)), None)
        mock_utime.assert_called_once_with(
            next(iter(vinfo.fds)),
            None,
            ns=(attr.st_atime_ns, os.fstat(next(iter(vinfo.fds))).st_mtime_ns),
            follow_symlinks=False)

    @patch('fusebox.fusefs.os.lstat')
    @patch('fusebox.fusefs.os.utime')
    def test_setattr_mtime_path(self, mock_utime, *_):
        ops, vinfo = self.setup_setattr()
        attr = MagicMock()
        needs = self.DefaultAttrDict(default=False, update_mtime=True)
        self._exec(ops.setattr, vinfo.vnode, attr, needs, None, None)
        mock_utime.assert_called_once_with(
            vinfo.path,
            None,
            ns=(os.lstat(vinfo.path).st_atime_ns, attr.st_mtime_ns),
            follow_symlinks=False)

    @patch('fusebox.fusefs.os.lstat')
    @patch('fusebox.fusefs.os.fstat')
    @patch('fusebox.fusefs.os.utime')
    def test_setattr_mtime_fd(self, mock_utime, *_):
        ops, vinfo = self.setup_setattr()
        attr = MagicMock()
        needs = self.DefaultAttrDict(default=False, update_mtime=True)
        self._exec(ops.setattr, None, attr, needs, next(iter(vinfo.fds)), None)
        mock_utime.assert_called_once_with(
            next(iter(vinfo.fds)),
            None,
            ns=(os.fstat(next(iter(vinfo.fds))).st_atime_ns, attr.st_mtime_ns),
            follow_symlinks=False)

    @patch('fusebox.fusefs.os.lstat')
    @patch('fusebox.fusefs.os.utime')
    def test_setattr_amtime_path(self, mock_utime, *_):
        ops, vinfo = self.setup_setattr()
        attr = MagicMock(st_atime_ns=123456, st_mtime_ns=234567)
        needs = self.DefaultAttrDict(default=False, update_atime=True, update_mtime=True)
        self._exec(ops.setattr, vinfo.vnode, attr, needs, None, None)
        mock_utime.assert_called_once_with(
            vinfo.path,
            None,
            ns=(attr.st_atime_ns, attr.st_mtime_ns),
            follow_symlinks=False)

    @patch('fusebox.fusefs.os.lstat')
    @patch('fusebox.fusefs.os.fstat')
    @patch('fusebox.fusefs.os.utime')
    def test_setattr_amtime_fd(self, mock_utime, *_):
        ops, vinfo = self.setup_setattr()
        attr = MagicMock(st_atime_ns=123456, st_mtime_ns=234567)
        needs = self.DefaultAttrDict(default=False, update_atime=True, update_mtime=True)
        self._exec(ops.setattr, None, attr, needs, next(iter(vinfo.fds)), None)
        mock_utime.assert_called_once_with(
            next(iter(vinfo.fds)),
            None,
            ns=(attr.st_atime_ns, attr.st_mtime_ns),
            follow_symlinks=False)

    @patch('fusebox.fusefs.os.lstat')
    def test_lookup(self, mock_lstat):
        ops = self.test_init()
        vinfo_a = ops.vm.create_vinfo()
        vinfo_a.add_path(self.PATH_SRC + '/dir1')
        vinfo_b = ops.vm.create_vinfo()
        vinfo_b.add_path(self.PATH_SRC + '/dir1/file1')
        attr = self._exec(ops.lookup, vinfo_a.vnode, os.fsencode('file1'))
        self.assertEqual(attr.st_ino, vinfo_b.vnode)

    @patch('fusebox.fusefs.Fusebox._getattr')
    @patch('fusebox.fusefs.pyfuse3.listdir')
    @patch('fusebox.fusefs.pyfuse3.readdir_reply')
    def test_readdir(self, mock_pfrep, mock_listdir, mock_getattr):
        ops = self.test_init()
        PARENT_DIR = self.PATH_SRC + '/other'
        vinfo_parent = ops.vm.create_vinfo()
        vinfo_parent.add_path(PARENT_DIR)
        mock_listdir.return_value = ['file1', 'file2']
        mock_getattr.return_value.st_ino = 3
        self._exec(ops.readdir, vnode=vinfo_parent.vnode, offset=0, token='ABCD')
        mock_listdir.assert_called_with(PARENT_DIR)
        mock_pfrep.assert_called_with(
            'ABCD',
            os.fsencode(mock_listdir.return_value[1]),
            mock_getattr.return_value,
            ops.vm.get(path=PARENT_DIR+'/file2').vnode)

    def test_open(self):
        ops = self.test_init()
        vinfo_a = ops.vm.create_vinfo()
        vinfo_a.add_path(self.PATH_SRC + '/file1')
        with patch('fusebox.fusefs.os.open') as mock_open:
            mock_open.side_effect = OSError(errno.ENOENT, 'Artifact Error')
            self.assertRaises(pyfuse3.FUSEError, self._exec, ops.open, vinfo_a.vnode, os.O_RDONLY, None)
        with patch('fusebox.fusefs.os.open') as mock_open:
            mock_open.return_value = 7
            finfo_a = self._exec(ops.open, vinfo_a.vnode, os.O_RDONLY, None)
            self.assertIsInstance(finfo_a, pyfuse3.FileInfo)
            self.assertEqual(finfo_a.fh, mock_open.return_value)

