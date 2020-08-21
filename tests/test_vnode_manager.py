import unittest
import os
from unittest.mock import MagicMock, patch
from fusebox import vnode


class TestVnodeManager(unittest.TestCase):
    RPATH = '/test/root/path'

    @patch('fusebox.vnode.os')
    @patch('fusebox.vnode.pyfuse3')
    def test_make_instance(self, mock_pyfuse3, mock_os):
        mock_pyfuse3.ROOT_INODE = 1
        mock_os.path.isdir.return_value = True
        mock_os.path.exists.return_value = True
        mock_os.path.abspath = os.path.abspath
        vm = vnode.VnodeManager(self.RPATH)
        self.assertEqual(vm.vnode_payout_max_num, 1)
        vinfo = vm.get(vnode=1)
        self.assertIsInstance(vinfo, vnode.VnodeInfo)
        self.assertEqual(vinfo.paths, {self.RPATH})

    @classmethod
    @patch('fusebox.vnode.os')
    @patch('fusebox.vnode.pyfuse3')
    def configure_a(cls, mock_pyfuse3, mock_os):
        mock_pyfuse3.ROOT_INODE = 1
        mock_os.path.isdir.return_value = True
        mock_os.path.exists.return_value = True
        mock_os.path.abspath = os.path.abspath
        vm = vnode.VnodeManager(cls.RPATH)
        vinfo_a = vm.create_vinfo_physical()
        vinfo_a.add_path(cls.RPATH + '2')
        vinfo_b = vm.create_vinfo_physical()
        vinfo_b.add_path(cls.RPATH + '3')
        vinfo_b.open_vnode(5, cls.RPATH + '3', 0)
        return vm, vinfo_a, vinfo_b

    @patch('fusebox.vnode.os')
    def test_get(self, mock_os):
        vm, *_ = self.configure_a()
        mock_os.path.exists.return_value = True
        mock_os.path.abspath = os.path.abspath
        vinfo = vm.get(vnode=1)
        self.assertEqual(vinfo.vnode, 1)
        self.assertEqual(vinfo.paths, {self.RPATH})
        vinfo = vm.get(vnode=2)
        self.assertEqual(vinfo.vnode, 2)
        self.assertEqual(vinfo.paths, {self.RPATH + '2'})
        vinfo = vm.get(path=self.RPATH + '3')
        self.assertEqual(vinfo.vnode, 3)
        self.assertEqual(vinfo.paths, {self.RPATH + '3'})
        vinfo = vm.get(fd=5)
        self.assertEqual(vinfo.vnode, 3)
        self.assertEqual(vinfo.paths, {self.RPATH + '3'})
        self.assertIn(5, vinfo.fds)
        self.assertEqual(vinfo.opencount, 1)

    @patch('fusebox.vnode.os')
    def test_getitem(self, mock_os):
        vm, vinfo_a, *_ = self.configure_a()
        mock_os.path.exists.return_value = True
        mock_os.path.abspath = os.path.abspath
        self.assertEqual(vm[2], vinfo_a)
        self.assertEqual(vm[self.RPATH + '2'], vinfo_a)
        self.assertRaises(KeyError, vm.__getitem__, 4)
        self.assertRaises(KeyError, vm.__getitem__, self.RPATH + '4')
        self.assertRaises(TypeError, vm.__getitem__, [])

    @patch('fusebox.vnode.os')
    def test_contains(self, mock_os):
        vm, *_ = self.configure_a()
        self.assertIn(2, vm)
        self.assertIn(self.RPATH + '2', vm)
        self.assertNotIn(4, vm)
        self.assertNotIn(self.RPATH + '4', vm)
        self.assertRaises(TypeError, vm.__contains__, [])

    def test_payout_vnode_num(self):
        vm, *_ = self.configure_a()
        self.assertEqual(vm.vnode_payout_max_num, 3)
        self.assertEqual(vm.payout_vnode_num(), 4)
        self.assertEqual(vm.vnode_payout_max_num, 4)

    def test_create_vinfo(self):
        vm, *_ = self.configure_a()
        self.assertIsInstance(vm.create_vinfo_physical(), vnode.VnodeInfo)

    @patch('fusebox.vnode.os')
    def test_vinfo_bind(self, mock_os):
        mock_os.path.exists.return_value = True
        mock_os.path.abspath = os.path.abspath
        vm, mock_vinfo = self.test_notify_path_add()
        vm.notify_vinfo_bind(mock_vinfo)
        self.assertIn(mock_vinfo.vnode, vm)
        return vm, mock_vinfo

    @patch('fusebox.vnode.os')
    def test_vinfo_unbind(self, mock_os):
        mock_os.path.exists.return_value = True
        mock_os.path.abspath = os.path.abspath
        vm, mock_vinfo = self.test_vinfo_bind()
        vm.notify_vinfo_unbind(mock_vinfo)
        self.assertNotIn(mock_vinfo.vnode, vm)
        self.assertNotIn(self.RPATH + '/Magic_a', vm)

    @patch('fusebox.vnode.os')
    def test_notify_path_add(self, mock_os):
        mock_os.path.exists.return_value = True
        mock_os.path.abspath = os.path.abspath
        vm, *_ = self.configure_a()
        mock_vinfo = MagicMock()
        mock_vinfo.manager = vm
        mock_vinfo.vnode = 4
        vm._vnodes[4] = mock_vinfo
        mock_vinfo.paths = {self.RPATH + '/Magic_a', self.RPATH + '/Magic_b'}
        vm.notify_path_add(mock_vinfo, self.RPATH + '/Magic_a')
        vm.notify_path_add(mock_vinfo, self.RPATH + '/Magic_b')
        self.assertIn(self.RPATH + '/Magic_a', vm)
        return vm, mock_vinfo

    @patch('fusebox.vnode.os')
    def test_notify_path_remove(self, mock_os):
        mock_os.path.exists.return_value = True
        mock_os.path.abspath = os.path.abspath
        vm, mock_vinfo = self.test_notify_path_add()
        mock_vinfo.paths.remove(self.RPATH + '/Magic_a')
        vm.notify_path_remove(mock_vinfo, self.RPATH + '/Magic_a')
        self.assertNotIn(self.RPATH + '/Magic_a', vm)

    @patch('fusebox.vnode.os')
    def test_notify_fd_open(self, mock_os):
        mock_os.path.exists.return_value = True
        mock_os.path.abspath = os.path.abspath
        vm, *_ = self.configure_a()
        mock_vinfo = MagicMock()
        mock_vinfo.manager = vm
        mock_vinfo.vnode = 4
        vm._vnodes[4] = mock_vinfo
        mock_vinfo.paths = {self.RPATH + '/Magic_a', self.RPATH + '/Magic_b'}
        vm._paths[self.RPATH + '/Magic_a'] = 4
        vm._paths[self.RPATH + '/Magic_b'] = 4
        mock_vinfo.fds = {8, 9}
        vm.notify_fd_open(mock_vinfo, 8)
        vm.notify_fd_open(mock_vinfo, 9)
        self.assertEqual(vm.get(fd=8), mock_vinfo)
        return vm, mock_vinfo

    @patch('fusebox.vnode.os')
    def test_notify_fd_close(self, mock_os):
        mock_os.path.exists.return_value = True
        mock_os.path.abspath = os.path.abspath
        vm, mock_vinfo = self.test_notify_fd_open()
        mock_vinfo.fds.remove(8)
        vm.notify_fd_close(mock_vinfo, 8)
        self.assertRaises(KeyError, vm.get, fd=8)
