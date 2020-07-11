import typing as typ
import pyfuse3
import os
import errno

AbsPath = typ.NewType('AbsPath', str)
Vnode = typ.NewType('Vnode', int)
FD = typ.NewType('FD', int)


class VnodeInfo:
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
    def opencount(self) -> int:
        return len(self._fds)

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

    def add_path(self, path: AbsPath, inc_ref: bool = True) -> None:
        """Register the path. If inc_ref is False, keep reference counter."""
        if not os.path.exists(path):
            raise pyfuse3.FUSEError(errno.ENOENT)
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

    def cleanup_mapping(self) -> None:
        """Remove vnode mappings which is not exist in real FS

        Some operations (like link/unlink or rename) may break mappings.
        i.e. the parent directory is renamed.
        This method will confirm mappings and delete if it was invalid.
        """
        for p in self._paths.copy():
            p = os.path.abspath(p)
            if not os.path.exists(p):
                self._paths.remove(p)
                self.manager.notify_path_remove(self, p)

    def forget_reference(self, ref_count: int) -> None:
        """Decrements reference counter and remove from memory if no one reference it"""
        assert not self._fds  # vinfo must not be opened.
        assert ref_count > 0
        self.refcount -= ref_count
        if self.refcount <= 0:
            self.manager.notify_vinfo_unbind(self)

    def open_vnode(self, fd: FD) -> None:
        """Notifying file descriptor was opened"""
        self._fds.add(fd)
        self.manager.notify_fd_open(self, fd)

    def close_vnode(self, fd: FD) -> None:
        """Notifying file descriptor was closed"""
        self._fds.remove(fd)
        self.manager.notify_fd_close(self, fd)


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
        self._vnodes[pyfuse3.ROOT_INODE] = VnodeInfo(manager=self)
        self._vnodes[pyfuse3.ROOT_INODE].add_path(root_path)
        self._paths[root_path] = self._vnodes[pyfuse3.ROOT_INODE]
        self.vnode_payout_max_num = pyfuse3.ROOT_INODE

    def __getitem__(self, key: typ.Union[Vnode, AbsPath]) -> VnodeInfo:
        if isinstance(key, VnodeInfo):
            vinfo = key
        elif isinstance(key, int):
            vinfo = self._get_vinfo_by_vnode(Vnode(key))
        elif isinstance(key, str):
            vinfo = self._get_vinfo_by_path(AbsPath(key))
        else:
            raise TypeError
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

    def create_vinfo(self) -> VnodeInfo:
        """Create VnodeInfo and make under control of manager"""
        vinfo = VnodeInfo(manager=self)
        return vinfo
