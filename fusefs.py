import os
import errno
import stat
import pyfuse3
import logging
import faulthandler
from vnode import VnodeManager

faulthandler.enable()

_logger_root = logging.getLogger('Fusebox')
_opslog = _logger_root.getChild('operation')
_acslog = _logger_root.getChild('access')


class Fusebox(pyfuse3.Operations):

    enable_writeback_cache = False

    def __init__(self, path_source, path_dest):
        super().__init__()
        self.vm = VnodeManager(path_source)
        self._path_source = os.path.abspath(path_source)
        self._path_mountpoint = os.path.abspath(path_dest)
        stat_source = os.lstat(path_source)
        self._src_device = stat_source.st_dev
        self.stat_path_open_r = set()
        self.stat_path_open_w = set()
        self.stat_path_open_rw = set()

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
        return self._getattr(self.vm[vnode])

    def _getattr(self, vinfo):
        _opslog.debug('getattr path: {}, fd: {}'.format(vinfo.path, vinfo.fd))
        if self._path_mountpoint in vinfo.paths:
            raise pyfuse3.FUSEError(errno.ENOENT)
        try:
            stat_ = os.lstat(vinfo.path)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)

        entry = pyfuse3.EntryAttributes()
        # copy attrs from base FS.
        for attr in ('st_mode', 'st_nlink', 'st_uid', 'st_gid', 'st_rdev',
                     'st_size', 'st_atime_ns', 'st_mtime_ns', 'st_ctime_ns'):
            setattr(entry, attr, getattr(stat_, attr))
        entry.st_ino = vinfo.vnode
        entry.generation = 0
        entry.entry_timeout = 0
        entry.attr_timeout = 0
        entry.st_blksize = 512
        entry.st_blocks = ((entry.st_size+entry.st_blksize-1) // entry.st_blksize)

        return entry

    async def setattr(self, vnode, attr, needs, fd, ctx):
        if fd is None:
            pofd = self.vm[vnode].path
            trunc = os.truncate
            chmod = os.chmod
            chown = os.chown
            fstat = os.lstat
        else:
            pofd = fd
            trunc = os.ftruncate
            chmod = os.fchmod
            chown = os.fchown
            fstat = os.fstat

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

        return await self.getattr(vnode)

    async def getxattr(self, vnode, name_enced, ctx):
        name = os.fsdecode(name_enced)
        path = self.vm[vnode].path
        try:
            return os.getxattr(path, name)
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
            self.vm[vnode].forget_reference(nlookup)

    async def lookup(self, vnode_parent, name_enced, ctx=None):
        name = os.fsdecode(name_enced)
        path = self.vm.make_path(self.vm[vnode_parent].path, name)
        try:
            vinfo = self.vm[path]
        except KeyError:
            vinfo = self.vm.create_vinfo()
        _opslog.debug("lookup called with path: {}".format(path))
        if name != '.' and name != '..':
            vinfo.add_path(path)
        return self._getattr(vinfo)

    async def opendir(self, vnode, ctx):
        _acslog.info('OPENDIR: {}'.format(self.vm[vnode].paths))
        return vnode

    async def readdir(self, vnode, offset, token):
        p_vinfo = self.vm[vnode]
        entries = list()
        _opslog.debug('readdir called: {}'.format(p_vinfo.path))
        for name in pyfuse3.listdir(p_vinfo.path):
            if name == '.' or name == '..':
                continue
            if os.path.join(p_vinfo.path, name) == self._path_mountpoint:  # FIXME: handle hardlinks
                continue
            attr = os.lstat(self.vm.make_path(p_vinfo.path, name))
            entries.append((attr.st_ino, name, attr))

        _opslog.debug('read %d entries, starting at %d', len(entries), offset)
        # FIXME: result is break if entries is changed between two calls to readdir()
        for (ino, name, attr) in sorted(entries):
            if ino <= offset:
                continue
            want_next_entry = pyfuse3.readdir_reply(token, os.fsencode(name), attr, ino)
            if not want_next_entry:
                break
            # Don't count up lookup_count if want_next_entry == False
            c_vinfo = self.vm.create_vinfo()
            c_path = self.vm.make_path(p_vinfo.path, name)
            c_vinfo.add_path(c_path)

    async def mkdir(self, vnode_parent, name, mode, ctx):
        path = self.vm.make_path(self.vm[vnode_parent].path, os.fsdecode(name))
        try:
            os.mkdir(path, mode=(mode & ~ctx.umask))
            os.chown(path, ctx.uid, ctx.gid)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        vinfo_c = self.vm.create_vinfo()
        vinfo_c.add_path(path)
        _acslog.info('MKDIR: {}'.format(path))
        return self._getattr(vinfo_c)

    async def rmdir(self, vnode_parent, name, ctx):
        path = self.vm.make_path(self.vm[vnode_parent].path, os.fsdecode(name))
        vinfo = self.vm[path]
        try:
            os.rmdir(path)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        vinfo.remove_path(path)
        _acslog.info('RMDIR: {}'.format(path))

    async def open(self, vnode, flags, ctx):
        vinfo = self.vm[vnode]
        fd = vinfo.open_vnode(flags)
        # Record accessed files;
        if flags & os.O_RDWR:
            self.stat_path_open_rw.add(vinfo.path)
        elif flags & os.O_WRONLY:
            self.stat_path_open_w.add(vinfo.path)
        else:
            self.stat_path_open_r.add(vinfo.path)

        _acslog.info('OPEN: {}'.format(vinfo.path))
        return pyfuse3.FileInfo(fh=fd)

    async def read(self, fd, offset, length):
        os.lseek(fd, offset, os.SEEK_SET)
        _acslog.info('READ: {}'.format(self._inode_path_map[self._fd_inode_map[fd]]))
        return os.read(fd, length)

    async def create(self, vnode_parent, name, mode, flags, ctx):
        path = self.vm.make_path(self.vm[vnode_parent].path, os.fsdecode(name))
        vinfo = self.vm.create_vinfo()
        vinfo.add_path(path)
        fd = vinfo.open_vnode(flags | os.O_CREAT | os.O_TRUNC, mode)
        _acslog.info('CREATE: {}'.format(path))
        return pyfuse3.FileInfo(fh=fd), self._getattr(vinfo)

    async def write(self, fd, offset, buf):
        os.lseek(fd, offset, os.SEEK_SET)
        _acslog.info('WRITE: {}'.format(self._inode_path_map[self._fd_inode_map[fd]]))
        return os.write(fd, buf)

    async def release(self, fd):
        fd = os.fdopen(fd)
        path = self.vm.make_path(fd.name)
        self.vm[path].close_vnode()

    async def rename(self, vnode_old_parent, name_old_enced, vnode_new_parent, name_new_enced, flags, ctx):
        name_old = os.fsdecode(name_old_enced)
        name_new = os.fsdecode(name_new_enced)
        vinfo_old_p = self.vm[vnode_old_parent]
        vinfo_new_p = self.vm[vnode_new_parent]
        path_old = self.vm.make_path(vinfo_old_p.path, name_old)
        path_new = self.vm.make_path(vinfo_new_p.path, name_new)
        try:
            os.rename(path_old, path_new)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        _acslog.info('RENAME: {} -> {}'.format(path_old, path_new))
        if path_old in self.vm:
            vinfo = self.vm[path_old]
            vinfo.add_path(path_new, inc_ref=False)
            vinfo.remove_path(path_old)

    async def link(self, vnode, vnode_new_parent, name_new_enced, ctx):
        name_new = os.fsdecode(name_new_enced)
        vinfo_new_p = self.vm[vnode_new_parent]
        path = self.vm.make_path(vinfo_new_p.path, name_new)
        vinfo = self.vm[vnode]
        try:
            os.link(self.vm[vnode].path, path, follow_symlinks=False)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        vinfo.add_path(path)
        _acslog.info('LINK: {}'.format(path))
        return await self._getattr(vinfo)

    async def unlink(self, vnode_parent, name_enced, ctx):
        name = os.fsdecode(name_enced)
        vinfo_p = self.vm[vnode_parent]
        path = self.vm.make_path(vinfo_p.path, name)
        vinfo = self.vm[path]
        try:
            os.unlink(path)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        vinfo.remove_path(path)
        _acslog.info('UNLINK: {}'.format(path))

    async def symlink(self, vnode_dst_parent, dst_enced, src_enced, ctx):
        name_src = os.fsdecode(src_enced)
        name_dst = os.fsdecode(dst_enced)
        vinfo_dst_p = self.vm[vnode_dst_parent]
        path_dst = self.vm.make_path(vinfo_dst_p.path, name_dst)
        try:
            os.symlink(name_src, path_dst)
            os.chown(path_dst, ctx.uid, ctx.gid, follow_symlinks=False)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        vinfo_dst = self.vm.create_vinfo()
        vinfo_dst.add_path(path_dst)
        return await self._getattr(vinfo_dst)