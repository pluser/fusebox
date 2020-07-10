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
        self.fd: typ.Optional[FD] = None
        self.refcount: int = 0
        self.opencount: int = 0

        self.vnode: Vnode = manager.payout_vnode_num()
        self.manager.notify_vinfo_bind(self)

    def __del__(self):
        assert self.refcount == 0
        assert self.opencount == 0
        assert self.fd is None
        self.manager.notify_vinfo_unbind(self)
        self.manager = None

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

    def add_path(self, path: typ.Union[AbsPath, str], inc_ref: bool = True) -> None:
        """Register the path. If inc_ref is False, keep reference counter."""
        if not os.path.exists(path):
            raise pyfuse3.FUSEError(errno.ENOENT)
        abspath = os.path.abspath(path)
        assert abspath in self.manager
        self._paths.add(abspath)
        if inc_ref:
            self.refcount += 1
        self.manager.notify_path_add(self, path)

    def remove_path(self, path: AbsPath) -> None:
        """Unregister the path"""
        abspath = os.path.abspath(path)
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
        assert self.fd is None  # vinfo must not be opened.
        assert ref_count > 0
        self.refcount -= ref_count
        if self.refcount <= 0:
            self.manager.notify_vinfo_unbind(self)

    def open_vnode(self, flags: typ.Optional[int], mode: typ.Optional[int] = 0o777) -> FD:
        """Return a file descriptor. if the file has opened already, simply return it"""
        self.opencount += 1
        if self.opencount <= 1:
            assert self.fd is None
            try:
                self.fd = typ.cast(FD, os.open(self.path, flags, mode))
            except OSError as exc:
                raise pyfuse3.FUSEError(exc.errno)
        assert self.fd is not None
        return self.fd

    def close_vnode(self) -> None:
        """Close the file descriptor if it is needed"""
        assert self.fd is not None
        self.opencount -= 1
        if self.opencount <= 0:
            try:
                os.close(self.fd)
            except OSError as exc:
                raise pyfuse3.FUSEError(exc.errno)
            self.fd = None


class VnodeManager:
    def __init__(self, root_path: AbsPath) -> None:
        super().__init__()
        self._vnodes: typ.Dict[Vnode, VnodeInfo] = dict()
        self._paths: typ.Dict[AbsPath, VnodeInfo] = dict()
        self.vnode_payout_max_num: Vnode = typ.cast(Vnode, 0)

        # install initial root vnode.
        if not os.path.isdir(root_path):
            raise RuntimeError
        self._vnodes[pyfuse3.ROOT_INODE] = VnodeInfo(manager=self)
        self._vnodes[pyfuse3.ROOT_INODE].add_path(root_path)
        self._paths[root_path] = self._vnodes[pyfuse3.ROOT_INODE]
        self.vnode_payout_max_num = pyfuse3.ROOT_INODE

    def __getitem__(self, key: typ.Union[Vnode, AbsPath]) -> typ.Optional[VnodeInfo]:
        vinfo = self._get_vinfo(key, ignore_error=True)
        if vinfo is None:
            raise KeyError
        vinfo.cleanup_mapping()
        return vinfo

    def __contains__(self, item):
        if isinstance(item, Vnode):
            return item in self._vnodes
        elif isinstance(item, AbsPath):
            return item in self._paths

    @staticmethod
    def make_path(*paths: typ.Union[AbsPath, str]) -> AbsPath:
        """Utility function. alias of `AbsPath(os.path.realpath(os.path.join(...)))`"""
        return AbsPath(os.path.realpath(os.path.join(*paths)))

    def _get_vinfo(self, vnode: typ.Union[Vnode, VnodeInfo, AbsPath], ignore_error=True) -> typ.Optional[VnodeInfo]:
        """Returns a VnodeInfo with exception handling.
        If ignore_error is True, None may be returned when given vnode is not exists."""
        try:
            if isinstance(vnode, VnodeInfo):
                assert vnode.manager == self
                vinfo = vnode
            elif isinstance(vnode, Vnode):
                vinfo = self._vnodes[vnode]
            elif isinstance(vnode, AbsPath):
                vnode = os.path.abspath(vnode)
                vinfo = self._paths[vnode]
            else:
                raise KeyError
        except KeyError:
            if ignore_error:
                vinfo = None
            else:
                raise pyfuse3.FUSEError(errno.ENOENT)
        return vinfo

    def notify_vinfo_bind(self, vinfo: VnodeInfo):
        """An interface to notify manager that the VnodeInfo is created and needed to be bind with manager"""
        assert vinfo.manager is None or vinfo.manager == self
        vinfo.manager = self
        self._vnodes[vinfo.vnode] = vinfo
        for p in vinfo.paths:
            assert p in self._paths
            self._paths[p] = vinfo

    def notify_vinfo_unbind(self, vinfo: VnodeInfo):
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

    def notify_path_add(self, vinfo: VnodeInfo, path: AbsPath):
        """An interface to notify manager that a path has been added"""
        assert vinfo.manager == self
        assert vinfo.vnode in self._vnodes
        assert path in vinfo.paths
        assert path not in self._paths
        self._paths[path] = vinfo

    def notify_path_remove(self, vinfo: VnodeInfo, path):
        """An interface to notify manager that a path has been removed"""
        assert vinfo.manager == self
        assert vinfo.vnode in self._vnodes
        assert path not in vinfo.paths
        if path in self._paths:
            del self._paths[path]

    def payout_vnode_num(self):
        self.vnode_payout_max_num += 1
        return self.vnode_payout_max_num

    def create_vinfo(self) -> VnodeInfo:
        """Create VnodeInfo and make under control of manager"""
        vinfo = VnodeInfo(manager=self)
        return vinfo
