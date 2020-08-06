import typing as typ
from abc import ABC
from collections import namedtuple
import pyfuse3
import os
import stat

AbsPath = typ.NewType('AbsPath', str)
Vnode = typ.NewType('Vnode', int)
FD = typ.NewType('FD', int)


class VnodeInfo(ABC):
    def __init__(self, manager: 'VnodeManager') -> None:
        """Create new VnodeInfo. Register to the container"""
        super().__init__()
        self.manager: VnodeManager = manager
        self._paths: typ.Set[AbsPath] = set()
        self._fds: typ.Set[FD] = set()
        self.refcount: int = 0

        self.vnode: Vnode = Vnode(manager.payout_vnode_num())
        self.manager.notify_vinfo_bind(self)

    def __delitem__(self):
        assert self.refcount == 0
        assert self.opencount == 0
        assert not self._fds
        self.manager.notify_vinfo_unbind(self)
        self.manager = None

    def __str__(self):
        return 'vinfo-{} path:{}'.format(self.vnode, next(iter(self._paths)))

    @property
    def virtual(self) -> bool:
        return isinstance(self, VnodeInfoPseudo)

    @property
    def opencount(self) -> int:
        return len(self._fds)

    @property
    def paths(self) -> typ.Set[AbsPath]:
        """Returns sort of absolute paths which is related in the vnode"""
        return self._paths.copy()

    @property
    def path(self) -> AbsPath:
        """Returns a representative absolute path which is related to the vnode"""
        return next(iter(self._paths))

    @property
    def fds(self) -> typ.Set[FD]:
        """Return a sort of file descriptor which is related in the vnode"""
        return self._fds.copy()

    @property
    def directory(self) -> bool:
        raise NotImplementedError

    @property
    def file(self) -> bool:
        raise NotImplementedError

    def add_path(self, path: AbsPath, inc_ref: bool = True) -> None:
        """Register the path. If inc_ref is False, keep reference counter."""
        abspath = os.path.abspath(path)
        self._paths.add(abspath)
        if inc_ref:
            self.refcount += 1
        self.manager.notify_path_add(self, path)

    def remove_path(self, path: AbsPath) -> None:
        """Unregister the path"""
        abspath = os.path.abspath(path)
        if abspath in self._paths:  # path may be removed by cleanup_mapping() already
            self._paths.remove(abspath)
        self.manager.notify_path_remove(self, path)
        if len(self._paths):
            self.manager.notify_vinfo_unbind(self)

    def open_vnode(self, fd: FD) -> None:
        """Notifying file descriptor was opened"""
        self._fds.add(fd)
        self.manager.notify_fd_open(self, fd)

    def close_vnode(self, fd: FD) -> None:
        """Notifying file descriptor was closed"""
        self._fds.remove(fd)
        self.manager.notify_fd_close(self, fd)

    def forget_reference(self, ref_count: int) -> None:
        """Decrements reference counter and remove from memory if no one reference it"""
        raise NotImplementedError

    def read(self, fd: int, offset: int, length: int) -> bytes:
        raise NotImplementedError

    def write(self, fd: int, offset: int, buf: bytes) -> int:
        raise NotImplementedError

    def listdir(self) -> typ.List[typ.Tuple[str, pyfuse3.EntryAttributes]]:
        raise NotImplementedError

    def getattr(self) -> pyfuse3.EntryAttributes:
        raise NotImplementedError


class VnodeInfoGenuine(VnodeInfo):
    def __init__(self, manager: 'VnodeManager') -> None:
        """Create new VnodeInfo. Register to the container"""
        super().__init__(manager)

    @property
    def paths(self) -> typ.Set[AbsPath]:
        """Returns sort of absolute paths which is related in the vnode"""
        self.cleanup_mapping()
        return self._paths.copy()

    @property
    def path(self) -> AbsPath:
        """Returns a representative absolute path which is related to the vnode"""
        self.cleanup_mapping()
        return next(iter(self._paths))

    @property
    def fds(self) -> typ.Set[FD]:
        """Return a sort of file descriptor which is related in the vnode"""
        return self._fds.copy()

    def cleanup_mapping(self) -> None:
        """Remove vnode mappings which is not exist in real FS

        Some operations (like link/unlink or rename) may break mappings.
        i.e. the parent directory is renamed.
        This method will confirm mappings and delete if it was invalid.
        """
        for p in self._paths.copy():
            p = os.path.abspath(p)
            if not os.path.lexists(p):  # don't remove vnode even if given p is symlink and it's broken
                self._paths.remove(p)
                self.manager.notify_path_remove(self, p)

    def forget_reference(self, ref_count: int) -> None:
        """Decrements reference counter and remove from memory if no one reference it"""
        assert not self._fds  # vinfo must not be opened.
        assert ref_count > 0
        self.refcount -= ref_count
        if self.refcount <= 0:
            self.manager.notify_vinfo_unbind(self)

    def read(self, fd: int, offset: int, length: int) -> bytes:
        os.lseek(fd, offset, os.SEEK_SET)
        return os.read(fd, length)

    def write(self, fd: int, offset: int, buf: bytes) -> int:
        os.lseek(fd, offset, os.SEEK_SET)
        return os.write(fd, buf)

    def getattr(self) -> pyfuse3.EntryAttributes:
        entry = pyfuse3.EntryAttributes()

        try:
            stat_ = os.lstat(self.path)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        # copy attrs from base FS.
        for attr in ('st_mode', 'st_nlink', 'st_uid', 'st_gid', 'st_rdev',
                     'st_size', 'st_atime_ns', 'st_mtime_ns', 'st_ctime_ns'):
            setattr(entry, attr, getattr(stat_, attr))
        entry.st_ino = self.vnode
        entry.generation = 0
        entry.entry_timeout = 0
        entry.attr_timeout = 0
        entry.st_blksize = 512
        entry.st_blocks = ((entry.st_size+entry.st_blksize-1) // entry.st_blksize)

        return entry

    def listdir(self) -> typ.List[typ.Tuple[str, pyfuse3.EntryAttributes]]:
        ent = list()
        files = namedtuple('files', 'name attr')
        for name in pyfuse3.listdir(self.path):
            if name == '.' or name == '..':
                continue  # exclude pseudo files and directories
            #if self.vm.path_mountpoint in (self.manager.make_path(p, name) for p in self.paths):
            #    continue  # Don't include mountpoint itself to directory entry
            if not os.path.lexists(self.manager.make_path(self.path, name)):
                continue  # listdir() returns invalid name for some reason. check if it exists and exclude it
            path = self.manager.make_path(self.path, name)
            vinfo_tmp = self.manager[path] if path in self.manager else self.manager.create_vinfo_physical()
            vinfo_tmp.add_path(path, inc_ref=False)
            attr = vinfo_tmp.getattr()
            ent.append(files(name, attr))
        return ent


class VnodeInfoPseudo(VnodeInfo):
    def __init__(self, manager: 'VnodeManager'):
        super().__init__(manager)
        # flags
        self.readonly = True
        self.persistent = True
        self.filemode = None

    @property
    def directory(self) -> bool:
        return stat.S_ISDIR(self.filemode)

    @property
    def file(self) -> bool:
        return stat.S_ISREG(self.filemode)

    def forget_reference(self, ref_count: int) -> None:
        """Decrements reference counter and remove from memory if no one reference it"""
        assert not self._fds  # vinfo must not be opened.
        assert ref_count > 0
        self.refcount -= ref_count

    def _getattr_common(self) -> pyfuse3.EntryAttributes:
        entry = pyfuse3.EntryAttributes()
        entry.st_mode = self.filemode
        entry.st_nlink = 1
        entry.st_uid = 0
        entry.st_gid = 0
        entry.st_rdev = 0
        entry.st_size = 0
        entry.st_atime_ns = 0
        entry.st_mtime_ns = 0
        entry.st_ctime_ns = 0
        entry.st_ino = self.vnode
        entry.generation = 0
        entry.entry_timeout = 0
        entry.attr_timeout = 0
        entry.st_blksize = 512
        entry.st_blocks = 0
        return entry


class VnodeManager:
    def __init__(self, root_path: AbsPath) -> None:
        super().__init__()
        self._vnodes: typ.Dict[Vnode, VnodeInfo] = dict()
        self._paths: typ.Dict[AbsPath, VnodeInfo] = dict()
        self._fds: typ.Dict[FD, VnodeInfo] = dict()
        self.vnode_payout_max_num: Vnode = Vnode(0)

        # install initial root vnode.
        if not os.path.isdir(root_path):
            raise RuntimeError
        self._vnodes[pyfuse3.ROOT_INODE] = VnodeInfoGenuine(manager=self)
        self._vnodes[pyfuse3.ROOT_INODE].add_path(root_path)
        self._paths[root_path] = self._vnodes[pyfuse3.ROOT_INODE]

    def __getitem__(self, key: typ.Union[Vnode, AbsPath]) -> VnodeInfo:
        if isinstance(key, VnodeInfo):
            vinfo = key
        elif isinstance(key, int):
            vinfo = self._get_vinfo_by_vnode(Vnode(key))
        elif isinstance(key, str):
            vinfo = self._get_vinfo_by_path(AbsPath(key))
        else:
            raise TypeError
        if isinstance(vinfo, VnodeInfoGenuine):
            vinfo.cleanup_mapping()
        return vinfo

    def __contains__(self, item: typ.Union[Vnode, AbsPath]) -> bool:
        if isinstance(item, int):
            return item in self._vnodes
        elif isinstance(item, str):
            return item in self._paths
        else:
            raise TypeError

    @staticmethod
    def make_path(*paths: typ.Union[AbsPath, str]) -> AbsPath:
        """Utility function. alias of `AbsPath(os.path.abspath(os.path.join(...)))`"""
        return AbsPath(os.path.abspath(os.path.join(*paths)))

    def _get_vinfo_by_vnode(self, vnode: Vnode) -> VnodeInfo:
        """Search for VnodeInfo with vnode number"""
        if isinstance(vnode, VnodeInfo):
            assert vnode.manager == self
            return vnode
        return self._vnodes[vnode]

    def _get_vinfo_by_path(self, path: AbsPath) -> VnodeInfo:
        """Search for VnodeInfo with path"""
        path = os.path.abspath(path)
        return self._paths[path]

    def _get_vinfo_by_fd(self, fd: FD) -> VnodeInfo:
        """Search for VnodeInfo with file descriptor"""
        return self._fds[fd]

    def get(self, vnode: Vnode = None, path: AbsPath = None, fd: FD = None) -> VnodeInfo:
        """Search and returns VnodeInfo"""
        if vnode:
            vinfo = self._get_vinfo_by_vnode(vnode)
        elif path:
            vinfo = self._get_vinfo_by_path(path)
        elif fd:
            vinfo = self._get_vinfo_by_fd(fd)
        else:
            raise RuntimeError
        if isinstance(vinfo, VnodeInfoGenuine):
            vinfo.cleanup_mapping()
        return vinfo

    def notify_vinfo_bind(self, vinfo: VnodeInfo) -> None:
        """An interface to notify manager that the VnodeInfo is created and needed to be bind with manager"""
        assert vinfo.manager is None or vinfo.manager == self
        vinfo.manager = self
        self._vnodes[vinfo.vnode] = vinfo
        for p in vinfo.paths:
            assert p in self._paths
            self._paths[p] = vinfo

    def notify_vinfo_unbind(self, vinfo: VnodeInfo) -> None:
        """An interface to notify manager that the VnodeInfo is going to be removed and needed to be unbind"""
        assert vinfo.manager is None or vinfo.manager == self
        vinfo.manager = None
        try:
            del self._vnodes[vinfo.vnode]
        except KeyError:
            pass  # removed already
        for p in vinfo.paths:
            if p in self._paths:
                try:
                    del self._paths[p]
                except KeyError:
                    pass

    def notify_path_add(self, vinfo: VnodeInfo, path: AbsPath) -> None:
        """An interface to notify manager that the path has been added. Idempotence"""
        assert vinfo.manager == self
        assert vinfo == self._vnodes[vinfo.vnode]
        assert path in vinfo.paths
        if path in self._paths and self._paths[path] != vinfo:
            # another vnode was assigned to given path.
            # this means the file on the given path is going to be overridden by the file on given vinfo.
            # so remove path from the vnode which is overridden.
            self._paths[path].remove_path(path)
        self._paths[path] = vinfo

    def notify_path_remove(self, vinfo: VnodeInfo, path) -> None:
        """An interface to notify manager that the path has been removed. Idempotence"""
        assert vinfo.manager == self
        assert vinfo == self._vnodes[vinfo.vnode]
        assert path not in vinfo.paths
        if path in self._paths:
            del self._paths[path]

    def notify_fd_open(self, vinfo: VnodeInfo, fd: FD) -> None:
        """An interface to notify manager that the fd has been opened. Idempotence"""
        assert vinfo.manager == self
        assert vinfo == self._vnodes[vinfo.vnode]
        assert fd in vinfo.fds
        if fd in self._fds:
            assert self._fds[fd] == vinfo
        else:
            self._fds[fd] = vinfo

    def notify_fd_close(self, vinfo: VnodeInfo, fd: FD) -> None:
        """An Interface to notify manager that the fd has been closed. Idempotence"""
        assert vinfo.manager == self
        assert vinfo == self._vnodes[vinfo.vnode]
        assert fd not in vinfo.fds
        if fd in self._fds:
            del self._fds[fd]

    def payout_vnode_num(self) -> Vnode:
        """Payout vnode number"""
        self.vnode_payout_max_num += 1
        return self.vnode_payout_max_num

    def create_vinfo_physical(self) -> VnodeInfoGenuine:
        """Create VnodeInfo and make under control of manager"""
        vinfo = VnodeInfoGenuine(manager=self)
        return vinfo

    def create_vinfo_virtual(self) -> VnodeInfoPseudo:
        """Create VnodeInfo and make under control of manager"""
        vinfo = VnodeInfoPseudo(manager=self)
        return vinfo
