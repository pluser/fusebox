import unittest
import os
import stat
import errno
from unittest.mock import MagicMock, patch
import pyfuse3
from fusebox import pseudo


class TestVnodeInfoPseudo(unittest.TestCase):
    @staticmethod
    def _exec(func, *args, **kwargs):
        return trio.run(functools.partial(func, *args, **kwargs))

    def test_ctl_root(self):
        manager = MagicMock()
        vinfo = pseudo.RootControllerVnodeInfo(manager=manager, path='/test/root/ctl')
        manager.notify_vinfo_bind.assert_called_with(vinfo)
        manager.notify_path_add.assert_called_with(vinfo, '/test/root/ctl')
        self.assertTrue(stat.S_ISDIR(vinfo.getattr().st_mode))  # Directory
        vinfo.files += ['acl', 'version']
        entries = vinfo.listdir()
        self.assertIn(('acl', manager.__getitem__.return_value.getattr.return_value), entries)
        self.assertIn(('version', manager.__getitem__.return_value.getattr.return_value), entries)

    def test_ctl_null(self):
        manager = MagicMock()
        vinfo = pseudo.NullVnodeInfo(manager=manager)
        manager.notify_vinfo_bind.assert_called_with(vinfo)
        self.assertTrue(stat.S_ISREG(vinfo.getattr().st_mode))  # Regular file
        self.assertEqual(vinfo.read(0, 0, 100), b'')
        self.assertEqual(vinfo.write(0, 0, b'foobar'), 6)
        self.assertEqual(vinfo.read(0, 0, 100), b'')

    def test_ctl_version(self):
        manager = MagicMock()
        vinfo = pseudo.VersionControllerVnodeInfo(manager=manager)
        manager.notify_vinfo_bind.assert_called_with(vinfo)
        self.assertTrue(stat.S_ISREG(vinfo.getattr().st_mode))  # Regular file
        self.assertEqual(vinfo.read(0, 0, 100), vinfo.content.encode())
        with self.assertRaises(pyfuse3.FUSEError) as e:
            vinfo.write(0, 0, b'foobar')
        self.assertEqual(e.exception.errno, errno.EACCES)  # Permission denied

    def test_ctl_acl(self):
        manager = MagicMock()
        auditor = MagicMock()
        vinfo = pseudo.AclControllerVnodeInfo(manager=manager, auditor=auditor)
        manager.notify_vinfo_bind.assert_called_with(vinfo)
        self.assertTrue(stat.S_ISREG(vinfo.getattr().st_mode))  # Regular file
        vinfo._contents = lambda: '#foobar\n'
        self.assertEqual(b'#foobar\n', vinfo.read(0, 0, 100))
        vinfo.write(0, len(vinfo._contents()), b'allowread /test/root/foo/bar')
        auditor.allowread.assert_called_with('/test/root/foo/bar')

    def test_ctl_acl_command(self):
        def enc(x):
            return x.encode('utf-8')
        mock_manager = MagicMock()
        mock_auditor = MagicMock()
        vinfo = pseudo.AclControllerVnodeInfo(manager=mock_manager, auditor=mock_auditor)

        vinfo.write(0, vinfo.getattr().st_size, enc('INVALID-ORDER /test/foo/bar'))
        mock_auditor.assert_not_called()
        mock_auditor.reset_mock()

        vinfo.write(0, vinfo.getattr().st_size, enc('allowread /test'))
        mock_auditor.allowread.assert_called_with('/test')
        mock_auditor.reset_mock()

        vinfo.write(0, vinfo.getattr().st_size, enc('allowwrite /test'))
        mock_auditor.allowwrite.assert_called_with('/test')
        mock_auditor.reset_mock()

        vinfo.write(0, vinfo.getattr().st_size, enc('denyread /test'))
        mock_auditor.denyread.assert_called_with('/test')
        mock_auditor.reset_mock()

        vinfo.write(0, vinfo.getattr().st_size, enc('denywrite /test'))
        mock_auditor.denywrite.assert_called_with('/test')
        mock_auditor.reset_mock()

        vinfo.write(0, vinfo.getattr().st_size, enc('discardwrite /test'))
        mock_auditor.discardwrite.assert_called_with('/test')
        mock_auditor.reset_mock()

        vinfo.write(0, vinfo.getattr().st_size, enc('addread /test'))
        mock_auditor.allowread.assert_called_with('/test')
        mock_auditor.reset_mock()

        vinfo.write(0, vinfo.getattr().st_size, enc('addwrite /test'))
        mock_auditor.allowread.assert_called_with('/test')
        mock_auditor.allowwrite.assert_called_with('/test')
        mock_auditor.reset_mock()

        vinfo.write(0, vinfo.getattr().st_size, enc('adddeny /test'))
        mock_auditor.denyread.assert_called_with('/test')
        mock_auditor.denywrite.assert_called_with('/test')
        mock_auditor.reset_mock()

        vinfo.write(0, vinfo.getattr().st_size, enc('addpredict /test'))
        mock_auditor.allowread.assert_called_with('/test')
        mock_auditor.discardwrite.assert_called_with('/test')
        mock_auditor.reset_mock()

    def test_ctl_acl_switch(self):
        manager = MagicMock()
        auditor = MagicMock()
        auditor.enabled = False
        vinfo = pseudo.AclSwitchControllerVnodeInfo(manager=manager, auditor=auditor)
        manager.notify_vinfo_bind.assert_called_with(vinfo)
        self.assertTrue(stat.S_ISREG(vinfo.getattr().st_mode))  # Regular file
        self.assertEqual(b'0', vinfo.read(0, 0, 100))
        vinfo.write(0, len(vinfo._contents), b'1\n')
        self.assertTrue(auditor.enabled)
        self.assertEqual(b'1', vinfo.read(0, 0, 100))
        vinfo.write(0, len(vinfo._contents), b'0\n')
        self.assertFalse(auditor.enabled)
