import unittest
from unittest.mock import MagicMock, patch
from fusebox import vnode
import os


class TestVnodeInfoGenuine(unittest.TestCase):
    TPATH = '/test/case/path'

    @classmethod
    @patch('fusebox.vnode.os.path.lexists', return_value=True)
    def configure_a(cls, manager, mock_mpe):
        vinfo = vnode.VnodeInfoGenuine(manager)
        vinfo.add_path(vnode.AbsPath(cls.TPATH + '1'))
        vinfo.add_path(vnode.AbsPath(cls.TPATH + '2'))
        return vinfo

    @patch('fusebox.vnode.os.path.lexists', return_value=True)
    def test_path(self, mock_ope):
        mock_vm = MagicMock()
        vinfo = self.configure_a(mock_vm)
        self.assertIn(vinfo.path, vinfo.paths)

    def test_make_instance(self):
        mock_vm = MagicMock()
        vinfo = vnode.VnodeInfo(mock_vm)
        mock_vm.notify_vinfo_bind.assert_called_with(vinfo)

    @patch('fusebox.vnode.os.path.lexists', return_value=True)
    def test_add_path(self, mock_ope):
        mock_vm = MagicMock()
        vinfo = vnode.VnodeInfo(mock_vm)
        self.assertEqual(0, vinfo.refcount)
        vinfo.add_path(vnode.AbsPath(self.TPATH))
        mock_vm.notify_path_add.assert_called_with(vinfo, self.TPATH)
        self.assertIn(self.TPATH, vinfo.paths)
        self.assertEqual(1, vinfo.refcount)
        vinfo.add_path(vnode.AbsPath(self.TPATH + '2'), inc_ref=False)
        self.assertEqual(1, vinfo.refcount)

    def test_remove_path(self):
        mock_vm = MagicMock()
        vinfo = self.configure_a(mock_vm)
        vinfo.remove_path(vnode.AbsPath(self.TPATH + '1'))
        mock_vm.notify_path_remove.assert_called_with(vinfo, self.TPATH + '1')
        self.assertNotIn(self.TPATH + '1', vinfo.paths)
        self.assertEqual(2, vinfo.refcount)

    def test_open_vnode(self):
        mock_vm = MagicMock()
        vinfo = self.configure_a(mock_vm)
        vinfo.open_vnode(129, self.TPATH + '/file1', 0)
        self.assertIn(129, vinfo.fds)
        mock_vm.notify_fd_open.assert_called_with(vinfo, 129)

    def test_close_vnode(self):
        mock_vm = MagicMock()
        vinfo = self.configure_a(mock_vm)
        vinfo.open_vnode(129, self.TPATH + '/file1', 0)
        self.assertIn(129, vinfo.fds)
        mock_vm.notify_fd_close(vinfo, 129)

    def test_clean_mapping(self):
        mock_vm = MagicMock()
        vinfo = self.configure_a(mock_vm)
        with patch('fusebox.vnode.os.path.lexists', return_value=True) as mock_ope:
            vinfo.cleanup_mapping()
            self.assertIn(self.TPATH + '1', vinfo.paths)
            self.assertIn(self.TPATH + '1', vinfo.paths)
            mock_vm.notify_path_remove.assert_not_called()
        mock_vm.reset_mock()
        with patch('fusebox.vnode.os.path.lexists') as mock_ope:
            mock_ope.side_effect = lambda p: True if p == self.TPATH + '1' else False
            vinfo.cleanup_mapping()
            self.assertIn(self.TPATH + '1', vinfo.paths)
            self.assertNotIn(self.TPATH + '2', vinfo.paths)
            self.assertEqual(vinfo.refcount, 2)
            mock_vm.notify_path_remove_with(vinfo, self.TPATH + '2')

    @patch('fusebox.vnode.os.path.lexists', return_value=True)
    def test_forget_reference(self, mock_ope):
        mock_vm = MagicMock()
        vinfo = self.configure_a(mock_vm)
        vinfo.add_path(self.TPATH + '2')
        self.assertEqual(vinfo.refcount, 3)
        vinfo.forget_reference(1)
        mock_vm.notify_vinfo_unbind.assert_not_called()
        vinfo.forget_reference(2)
        mock_vm.notify_vinfo_unbind.assert_called_with(vinfo)
