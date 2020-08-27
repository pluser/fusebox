import typing as typ
import io
import os
import errno
import re
import logging
import stat
import pyfuse3
from .vnode import VnodeManager, VnodeInfoPseudo, AbsPath
from .auditor import Auditor, Order

_logger_root = logging.getLogger('Fusebox')
_opslog = _logger_root.getChild('operation')
_acslog = _logger_root.getChild('access')


def construct_controllers(fusebox: 'Fusebox'):
    vm = fusebox.vm
    auditor = fusebox.auditor
    path_controller = os.path.join(fusebox.path_source, fusebox.CONTROLLER_FILENAME)

    vinfo_top = RootControllerVnodeInfo(vm, vm.make_path(fusebox.path_source, fusebox.CONTROLLER_FILENAME))  # FIXME: means for register vnodeinfo
    vinfo_top.add_path(vm.make_path(path_controller))
    vinfo_top.files.extend(['acl', 'acl_switch', 'version'])

    vinfo_acl = AclControllerVnodeInfo(vm, auditor)
    vinfo_acl.add_path(vm.make_path(path_controller, 'acl'))

    vinfo_acl_sw = AclSwitchControllerVnodeInfo(vm, auditor)
    vinfo_acl_sw.add_path(vm.make_path(path_controller, 'acl_switch'))

    vinfo_version = VersionControllerVnodeInfo(vm)
    vinfo_version.add_path(vm.make_path(path_controller, 'version'))


class RootControllerVnodeInfo(VnodeInfoPseudo):
    def __init__(self, manager: VnodeManager, path: AbsPath):
        super().__init__(manager)
        self.filemode = (
          stat.S_IFDIR
        | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
        | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP
        | stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH
        )
        self.add_path(path)
        self.files = list()

    def getattr(self) -> pyfuse3.EntryAttributes:
        entry = self._getattr_common()
        entry.st_nlink = 2
        return entry

    def listdir(self) -> typ.List[typ.Tuple[str, pyfuse3.EntryAttributes]]:
        return [(name, self.manager[self.manager.make_path(self.path, name)].getattr()) for name in self.files]


class AclControllerVnodeInfo(VnodeInfoPseudo):
    def __init__(self, manager: VnodeManager, auditor: Auditor):
        super().__init__(manager)
        self.auditor = auditor
        self.filemode = (
          stat.S_IFREG
        | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
        | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP
        | stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH
        )

    def _contents(self) -> str:
        string = str()

        string += '# Don\'t remove a next line\n'
        string += 'clearall'
        string += '\n\n'

        #string += '[Read]\n'
        for perm in self.auditor.permission_read:
            order = perm.order
            if order == Order.ALLOW:
                string += 'allowread'
            elif order == Order.DENY:
                string += 'denyread'
            string += ' '
            string += perm.path
            string += '\n'

        #string += '[Write]\n'
        for perm in self.auditor.permission_write:
            order = perm.order
            if order == Order.ALLOW:
                string += 'allowwrite'
            elif order == Order.DENY:
                string += 'denywrite'
            elif order == Order.DISCARD:
                string += 'discardwrite'
            string += ' '
            string += perm.path
            string += '\n'

        return string

    def getattr(self) -> pyfuse3.EntryAttributes:
        entry = self._getattr_common()
        entry.st_size = len(self._contents().encode())
        entry.st_blocks = ((entry.st_size + entry.st_blksize - 1) // entry.st_blksize)
        return entry

    def read(self, fd: int, offset: int, length: int) -> bytes:
        string = self._contents()
        buf = io.BytesIO(string.encode())
        buf.seek(offset)
        retval = buf.read(length)
        buf.close()
        return retval

    def write(self, fd: int, offset: int, buf: bytes) -> int:
        if os.O_TRUNC & self.manager.get(fd=fd).fdparam[fd].mode:
            print('WRITE_WITH_TRUNC')
            self.auditor.clearall()
            content = io.BytesIO(b'')
            print('offset: {}'.format(offset))
        else:
            content = io.BytesIO(self._contents().encode())
        content.seek(offset)
        content.write(buf)
        content.seek(0)
        for l in content.read().decode().splitlines():
            if l.startswith('#') or l == '':  # skip comment and blank lines
                continue
            match = re.fullmatch(r'^(?P<order>\S+)\s*(?P<args>.*)$', l)
            if not match:
                # FIXME: the warning should be supressed some statement
                _opslog.warning('Invalid Syntax. Input: <{}>'.format(l))
                continue
            _opslog.debug('ORDER: <{}>\t\tARGS: <{}>'.format(match.group('order'), match.group('args')))
            order = match.group('order').upper()
            path = os.path.abspath(match.group('args'))

            if not os.path.lexists(path):
                _opslog.warning('Given PATH <{}> does not exists.'.format(path))

            if order == 'CLEARALL':
                self.auditor.clearall()
                _opslog.info('Rules were completely cleared.'.format(path))

            elif order == 'ALLOWREAD' or order == 'ADDREAD':
                self.auditor.allowread(path)
                _opslog.info('Permitted reading from path <{}>.'.format(path))

            elif order == 'ALLOWWRITE':
                self.auditor.allowwrite(path)
                _opslog.info('Permitted writing to path <{}>.'.format(path))

            elif order == 'DENYREAD':
                self.auditor.denyread(path)
                _opslog.info('Prohibited reading to path <{}>.'.format(path))

            elif order == 'DENYWRITE':
                self.auditor.denywrite(path)
                _opslog.info('Prohibited writing to path <{}>.'.format(path))

            elif order == 'DISCARDWRITE':
                self.auditor.discardwrite(path)
                _opslog.info('Throwing away inputs to path <{}>.'.format(path))

            elif order == 'ADDWRITE':
                self.auditor.allowread(path)
                self.auditor.allowwrite(path)
                _opslog.info('Permitted reading/writing to path <{}>.'.format(path))

            elif order == 'ADDDENY':
                self.auditor.denyread(path)
                self.auditor.denywrite(path)
                _opslog.info('Prohibited reading/writing to path <{}>.'.format(path))

            elif order == 'ADDPREDICT':
                self.auditor.allowread(path)
                self.auditor.discardwrite(path)
                _opslog.info('Throwing away inputs to path <{}>.'.format(path))

            else:
                _opslog.warning('Unknown ORDER <{}>\twith ARGS <{}>. Ignored.'.format(order, path))

        content.close()
        return len(buf)


class AclSwitchControllerVnodeInfo(VnodeInfoPseudo):
    def __init__(self, manager: VnodeManager, auditor: Auditor):
        super().__init__(manager)
        self.auditor = auditor
        self.filemode = (
              stat.S_IFREG
            | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
            | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP
            | stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH
        )

    @property
    def _contents(self) -> str:
        if self.auditor.enabled:
            return '1'
        else:
            return '0'

    def getattr(self) -> pyfuse3.EntryAttributes:
        entry = self._getattr_common()
        entry.st_size = len(self._contents)
        return entry

    def read(self, fd: int, offset: int, length: int) -> bytes:
        cont = io.BytesIO((self._contents).encode())
        cont.seek(offset)
        retval = cont.read(length)
        cont.close()
        return retval

    def write(self, fd: int, offset: int, buf: bytes) -> int:
        cont = buf.decode()
        if cont[0] == '0':  # if first byte is zero, disable ACL feature
            self.auditor.enabled = False
            _acslog.info('Fusebox ACL disengaged.')
        elif cont[0] == '1':
            self.auditor.enabled = True
            _acslog.info('Fusebox ACL engaged.')
        else:  # if invalid input
            pyfuse3.FUSEError(errno.EINVAL)  # Invalid argument
        return len(buf)


class VersionControllerVnodeInfo(VnodeInfoPseudo):
    def __init__(self, manager: VnodeManager):
        super().__init__(manager)
        self.filemode = (
              stat.S_IFREG
            | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
            | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP
            | stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH
        )
        self.content = 'Fusebox version v0.1\n'

    def getattr(self) -> pyfuse3.EntryAttributes:
        entry = self._getattr_common()
        entry.st_size = len(self.content)
        return entry

    def read(self, fd: int, offset: int, length: int) -> bytes:
        cont = io.BytesIO(self.content.encode())
        cont.seek(offset)
        retval = cont.read(length)
        cont.close()
        return retval

    def write(self, fd: int, offset: int, buf: bytes) -> int:
        raise pyfuse3.FUSEError(errno.EACCES)


class NullVnodeInfo(VnodeInfoPseudo):
    def __init__(self, manager: VnodeManager):
        super().__init__(manager)
        self.filemode = (
          stat.S_IFREG
        | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
        | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP
        | stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH
        )

    def getattr(self) -> pyfuse3.EntryAttributes:
        entry = self._getattr_common()
        return entry

    def read(self, fd: int, offset: int, length: int) -> bytes:
        return b''

    def write(self, fd: int, offset: int, buf: bytes) -> int:
        return len(buf)
