import os
import re
import errno
import stat
import pyfuse3
import logging
import faulthandler
from .auditor import Auditor, Permission, Order
from .vnode import VnodeManager, FD
from .pseudo import construct_controllers, NullVnodeInfo

faulthandler.enable()

_logger_root = logging.getLogger('Fusebox')
_opslog = _logger_root.getChild('operation')
_acslog = _logger_root.getChild('access')


class Fusebox(pyfuse3.Operations):
    def __init__(self, path_source, path_dest):
        super().__init__()
        self.CONTROLLER_FILENAME = 'fuseboxctlv1'
        self.vm = VnodeManager(path_source)
        self.path_source = os.path.abspath(path_source)
        self.path_mountpoint = os.path.abspath(path_dest)
        self.auditor = Auditor()
        self.stat_path_open_r = set()
        self.stat_path_open_w = set()
        self.stat_path_open_rw = set()

        # add pseudo file
        construct_controllers(self)
        self.vinfo_ctl = self.vm[self.vm.make_path(self.path_source, self.CONTROLLER_FILENAME)]
        self.vinfo_null = NullVnodeInfo(self.vm)

    # noinspection PyUnusedLocal
    async def statfs(self, ctx):
        root = self.vm[pyfuse3.ROOT_INODE].path
        stat_ = pyfuse3.StatvfsData()
        try:
            statfs = os.statvfs(root)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        for attr in ('f_bsize', 'f_frsize', 'f_blocks', 'f_bfree', 'f_bavail',
                     'f_files', 'f_ffree', 'f_favail'):
            setattr(stat_, attr, getattr(statfs, attr))
        stat_.f_namemax = statfs.f_namemax - (len(root)+1)
        return stat_

    async def getattr(self, vnode, ctx=None):
        try:
            vinfo = self.vm[vnode]
        except KeyError:
            # when?
            raise pyfuse3.FUSEError(errno.ENOENT) # no such file or directory
        _opslog.debug('getattr path: {}, fd: {}'.format(vinfo.paths, vinfo.fds))
        if self.path_mountpoint in vinfo.paths:
            raise pyfuse3.FUSEError(errno.ENOENT)
        return vinfo.getattr()

    async def setattr(self, vnode, attr, needs, fd, ctx):
        if vnode:
            vinfo = self.vm[vnode]
            if vinfo.paths:
                pofd = vinfo.path
                trunc = os.truncate
                chmod = os.chmod
                chown = os.chown
                fstat = os.lstat
            elif vinfo.fds:
                # file is unlinked already, but opened.
                fd = list(vinfo.fds)[0]
            else:
                raise RuntimeError()
        if fd:
            vinfo = self.vm.get(fd=fd)
            pofd = fd
            trunc = os.ftruncate
            chmod = os.fchmod
            chown = os.fchown
            fstat = os.fstat
        if not vnode and not fd:
            # When?
            raise ValueError()

        if vinfo.virtual:
            return vinfo.getattr()

        try:
            if needs.update_size:
                trunc(pofd, attr.st_size)
            if needs.update_mode:
                chmod(pofd, stat.S_IMODE(attr.st_mode))
            if needs.update_uid:
                chown(pofd, attr.st_uid, -1, follow_symlinks=False)
            if needs.update_gid:
                chown(pofd, -1, attr.st_gid, follow_symlinks=False)
            if needs.update_atime and needs.update_mtime:
                # os.utime update both atime and mtime
                os.utime(pofd, None, ns=(attr.st_atime_ns, attr.st_mtime_ns), follow_symlinks=False)
            elif needs.update_atime:
                attr.st_mtime_ns = fstat(pofd).st_mtime_ns
                os.utime(pofd, None, ns=(attr.st_atime_ns, attr.st_mtime_ns), follow_symlinks=False)
            elif needs.update_mtime:
                attr.st_atime_ns = fstat(pofd).st_atime_ns
                os.utime(pofd, None, ns=(attr.st_atime_ns, attr.st_mtime_ns), follow_symlinks=False)

        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)

        return vinfo.getattr()

    async def getxattr(self, vnode, name_enced, ctx):
        name = os.fsdecode(name_enced)
        vinfo = self.vm[vnode]
        if vinfo.virtual:
            raise pyfuse3.FUSEError(errno.ENODATA)  # No data available
        else:
            try:
                return os.getxattr(vinfo.path, name)
            except OSError as exc:
                raise pyfuse3.FUSEError(exc.errno)

    async def setxattr(self, vnode, name_enced, value_enced, ctx):
        name = os.fsdecode(name_enced)
        path = self.vm[vnode].path
        try:
            os.setxattr(path, name, value_enced)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)

    async def removexattr(self, vnode, name_enced, ctx):
        name = os.fsdecode(name_enced)
        path = self.vm[vnode].path
        try:
            os.removexattr(path, name)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)

    async def listxattr(self, vnode, ctx):
        path = self.vm[vnode].path
        try:
            xattrs = os.listxattr(path)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        return list(map(os.fsencode, xattrs))

    async def readlink(self, vnode, ctx):
        path = self.vm[vnode].path
        try:
            target = os.readlink(path)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        return os.fsencode(target)

    async def forget(self, vnode_list):
        for (vnode, nlookup) in vnode_list:
            if vnode in self.vm:  # vnode may be forgotten already
                self.vm[vnode].forget_reference(nlookup)

    async def lookup(self, vnode_parent, name_enced, ctx=None):
        name = os.fsdecode(name_enced)
        path = self.vm.make_path(self.vm[vnode_parent].path, name)
        _opslog.debug("lookup called with path: {}".format(path))
        if self.path_mountpoint in (self.vm.make_path(p, name) for p in self.vm[vnode_parent].paths):
            raise pyfuse3.FUSEError(errno.ENOENT)  # Response that mountpoint is not exists.
        vinfo = self.vm[path] if path in self.vm else self.vm.create_vinfo_physical()
        if not os.path.lexists(path) and not vinfo.virtual:
            raise pyfuse3.FUSEError(errno.ENOENT)
        if name != '.' and name != '..':
            vinfo.add_path(path)
        return vinfo.getattr()

    async def opendir(self, vnode, ctx):
        _acslog.debug('OPENDIR: {}'.format(self.vm[vnode].paths))
        return vnode

    def _readdir(self, vinfo_p):
        ent = list()
        if self.path_source in vinfo_p.paths:
            # insert controller root node to directory entries
            name = self.CONTROLLER_FILENAME
            attr = self.vinfo_ctl.getattr()
            ent.append((attr.st_ino, name, attr))
        for name, attr in vinfo_p.listdir():
            ent.append((attr.st_ino, name, attr))
        return ent

    async def readdir(self, vnode, offset, token):
        vinfo_p = self.vm[vnode]
        entries = self._readdir(vinfo_p)
        _opslog.debug('read %d entries, starting at %d', len(entries), offset)
        # FIXME: result is break if entries is changed between two calls to readdir()
        if entries:  # asking empty directory? when?
            assert len(tuple(zip(*entries))[0]) == len(set(tuple(zip(*entries))[0]))  # entries must not duplicate
        for ino, name, attr in sorted(entries):
            if ino <= offset:
                continue
            assert ino in self.vm
            vinfo_c = self.vm[ino]
            want_next_entry = pyfuse3.readdir_reply(token, os.fsencode(name), attr, ino)
            if not want_next_entry:
                if vinfo_c.refcount == 0:  # if newly created in the above code
                    del vinfo_c
                break
            # Don't count up reference count if want_next_entry is False
            path_c = self.vm.make_path(vinfo_p.path, name)
            vinfo_c.add_path(path_c)
        _acslog.debug('READDIR: {}'.format(vinfo_p.path))

    async def mknod(self, parent_inode, name, mode, rdev, ctx):
        vinfo_p = self.vm[parent_inode]
        path = self.vm.make_path(vinfo_p.path, os.fsdecode(name))
        if self.auditor.ask_discard(path):
            _acslog.debug('MKDIR-FAKE: {}'.format(path))
            attr = self.vinfo_null.getattr()
            attr.st_mode = mode & ~ctx.umask
            return attr
        try:
            os.mknod(path, mode=(mode & ~ctx.umask), device=rdev)
            os.chown(path, ctx.uid, ctx.gid)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        vinfo_c = self.vm.create_vinfo_physical()
        vinfo_c.add_path(path)
        _acslog.debug('MKNOD: {}'.format(path))
        return vinfo_c.getattr()

    async def mkdir(self, vnode_parent, name, mode, ctx):
        path = self.vm.make_path(self.vm[vnode_parent].path, os.fsdecode(name))
        if not self.auditor.ask_writable(path):
            raise pyfuse3.FUSEError(errno.EACCES)  # Permission denied
        if self.auditor.ask_discard(path):
            _acslog.debug('MKDIR-FAKE: {}'.format(path))
            attr = self.vinfo_null.getattr()
            attr.st_mode &= ~stat.S_IFREG  # make sure this is not regular file
            attr.st_mode |= stat.S_IFDIR  # make sure this is directory
            return attr
        try:
            os.mkdir(path, mode=(mode & ~ctx.umask))
            os.chown(path, ctx.uid, ctx.gid)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        vinfo_c = self.vm.create_vinfo_physical()
        vinfo_c.add_path(path)
        _acslog.debug('MKDIR: {}'.format(path))
        return vinfo_c.getattr()

    async def rmdir(self, vnode_parent, name, ctx):
        path = self.vm.make_path(self.vm[vnode_parent].path, os.fsdecode(name))
        vinfo = self.vm[path]
        if not self.auditor.ask_writable(path):
            raise pyfuse3.FUSEError(errno.EACCES)  # Permission denied
        if self.auditor.ask_discard(path):
            _acslog.debug('RMDIR-FAKE: {}'.format(path))
            return
        try:
            os.rmdir(path)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        vinfo.remove_path(path)
        _acslog.debug('RMDIR: {}'.format(path))

    async def open(self, vnode, flags, ctx):
        vinfo = self.vm[vnode]
        _acslog.debug('OPEN: {}'.format(vinfo.path))
        if vinfo.virtual:
            fd = FD(os.open('/dev/null', flags))  # reserve file descriptor number
            vinfo.open_vnode(fd, '/dev/null', flags, discard=False)
            return pyfuse3.FileInfo(fh=fd)
        elif self.auditor.ask_discard(vinfo.path):
            try:
                # open with readonly mode
                fd = FD(os.open(vinfo.path, flags & ~(os.O_TRUNC | os.O_RDWR | os.O_WRONLY) | os.O_RDONLY))
            except OSError as exc:
                raise pyfuse3.FUSEError(exc.errno)
            vinfo.open_vnode(fd, vinfo.path, flags & ~(os.O_TRUNC | os.O_RDWR | os.O_WRONLY) | os.O_RDONLY, discard=True)
            return pyfuse3.FileInfo(fh=fd)
        else:
            if flags & os.O_RDWR and not (self.auditor.ask_writable(vinfo.path) and self.auditor.ask_readable(vinfo.path)):
                _opslog.info('Reading and writing to PATH <{}> is not permitted.'.format(vinfo.path))
                raise pyfuse3.FUSEError(errno.EACCES)  # Permission denied
            if flags & os.O_WRONLY and not self.auditor.ask_writable(vinfo.path):
                _opslog.info('Writing to PATH <{}> is not permitted.'.format(vinfo.path))
                raise pyfuse3.FUSEError(errno.EACCES)  # Permission denied
            if not flags & (os.O_RDWR | os.O_WRONLY) and not self.auditor.ask_readable(vinfo.path):
                _opslog.info('Reading from PATH <{}> is not permitted.'.format(vinfo.path))
                raise pyfuse3.FUSEError(errno.EACCES)  # Permission denied
            try:
                fd = FD(os.open(vinfo.path, flags))
            except OSError as exc:
                raise pyfuse3.FUSEError(exc.errno)
            # Record accessed files;
            if flags & os.O_RDWR:
                self.stat_path_open_rw.add(vinfo.path)
            elif flags & os.O_WRONLY:
                self.stat_path_open_w.add(vinfo.path)
            else:
                self.stat_path_open_r.add(vinfo.path)
            vinfo.open_vnode(fd, vinfo.path, flags, discard=False)
            return pyfuse3.FileInfo(fh=fd)

    async def read(self, fd, offset, length):
        vinfo = self.vm.get(fd=fd)
        _acslog.debug('READ: {}'.format(vinfo))
        return vinfo.read(fd, offset, length)

    async def create(self, vnode_parent, name, mode, flags, ctx):
        path = self.vm.make_path(self.vm[vnode_parent].path, os.fsdecode(name))
        if path in self.vm and self.vm[path].virtual:
            raise pyfuse3.FUSEError(errno.EACCES)  # Permission denied, since pseudo file should not be created.
        if not self.auditor.ask_writable(path):
            _opslog.info('Creating to PATH <{}> is not permitted.'.format(path))
            raise pyfuse3.FUSEError(errno.EACCES)  # Permission denied
        if self.auditor.ask_discard(path):
            try:
                fd = FD(os.open('/dev/null', flags & ~os.O_CREAT))
            except OSError as exc:
                raise pyfuse3.FUSEError(exc.errno)
            self.vinfo_null.open_vnode(fd, '/dev/null', flags & ~os.O_CREAT, discard=True)
            self.vinfo_null.add_path(path)
            _acslog.debug('CREATE-FAKE: {}'.format(path))
            return pyfuse3.FileInfo(fh=fd), self.vinfo_null.getattr()

        vinfo = self.vm.create_vinfo_physical()
        try:
            fd = FD(os.open(path, flags | os.O_CREAT | os.O_TRUNC, mode))
            os.chown(path, ctx.uid, ctx.gid, follow_symlinks=False)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        vinfo.add_path(path)
        vinfo.open_vnode(fd, path, flags | os.O_CREAT | os.O_TRUNC, discard=False)
        _acslog.debug('CREATE: {}'.format(path))
        return pyfuse3.FileInfo(fh=fd), vinfo.getattr()

    async def write(self, fd, offset, buf):
        vinfo = self.vm.get(fd=fd)
        _acslog.debug('WRITE: {}'.format(vinfo))
        if not vinfo.virtual and vinfo.fdparam[fd].discard:
            return len(buf)
        return vinfo.write(fd, offset, buf)

    async def release(self, fd):
        try:
            os.close(fd)
        except OSError as exc:
            pyfuse3.FUSEError(exc.errno)
        self.vm.get(fd=fd).close_vnode(fd)

    async def rename(self, vnode_old_parent, name_old_enced, vnode_new_parent, name_new_enced, flags, ctx):
        name_old = os.fsdecode(name_old_enced)
        name_new = os.fsdecode(name_new_enced)
        vinfo_old_p = self.vm[vnode_old_parent]
        vinfo_new_p = self.vm[vnode_new_parent]
        path_old = self.vm.make_path(vinfo_old_p.path, name_old)
        path_new = self.vm.make_path(vinfo_new_p.path, name_new)
        if not self.auditor.ask_writable(path_new):
            raise pyfuse3.FUSEError(errno.EACCES)  # Permission denied
        try:
            os.rename(path_old, path_new)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        _acslog.debug('RENAME: {} -> {}'.format(path_old, path_new))
        if path_old in self.vm:
            vinfo = self.vm[path_old]
            vinfo.add_path(path_new, inc_ref=False)
            vinfo.remove_path(path_old)

    async def link(self, vnode, vnode_new_parent, name_new_enced, ctx):
        name_new = os.fsdecode(name_new_enced)
        vinfo_new_p = self.vm[vnode_new_parent]
        path = self.vm.make_path(vinfo_new_p.path, name_new)
        vinfo = self.vm[vnode]
        if not self.auditor.ask_writable(path):
            raise pyfuse3.FUSEError(errno.EACCES)  # Permission denied
        if self.auditor.ask_discard(path):
            _acslog.debug('LINK-FAKE: {}'.format(path))
            return self.vinfo_null.getattr()
        try:
            os.link(self.vm[vnode].path, path, follow_symlinks=False)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        vinfo.add_path(path)
        _acslog.debug('LINK: {}'.format(path))
        return vinfo.getattr()

    async def unlink(self, vnode_parent, name_enced, ctx):
        name = os.fsdecode(name_enced)
        vinfo_p = self.vm[vnode_parent]
        path = self.vm.make_path(vinfo_p.path, name)
        vinfo = self.vm[path]
        if not self.auditor.ask_writable(path):
            raise pyfuse3.FUSEError(errno.EACCES)  # Permission denied
        if self.auditor.ask_discard(path):
            _acslog.debug('UNLINK-FAKE: {}'.format(path))
            return
        try:
            os.unlink(path)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        vinfo.remove_path(path)
        _acslog.debug('UNLINK: {}'.format(path))

    async def symlink(self, vnode_dst_parent, dst_enced, src_enced, ctx):
        name_src = os.fsdecode(src_enced)
        name_dst = os.fsdecode(dst_enced)
        vinfo_dst_p = self.vm[vnode_dst_parent]
        path_dst = self.vm.make_path(vinfo_dst_p.path, name_dst)
        if not self.auditor.ask_writable(path_dst):
            raise pyfuse3.FUSEError(errno.EACCES)  # Permission denied
        if self.auditor.ask_discard(path_dst):
            _acslog.debug('SYMLINK-FAKE: {}'.format(path_dst))
            return self.vinfo_null.getattr()
        try:
            os.symlink(name_src, path_dst)
            os.chown(path_dst, ctx.uid, ctx.gid, follow_symlinks=False)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        vinfo_dst = self.vm.create_vinfo_physical()
        vinfo_dst.add_path(path_dst)
        _acslog.debug('SYMLINK: {}'.format(path_dst))
        return vinfo_dst.getattr()
