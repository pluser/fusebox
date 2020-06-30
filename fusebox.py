#!/usr/bin/python3
# -*- coding: utf-8 -*-
'''
fusebox.py - Entry point of FUSE-powered sandbox system
'''

from collections import defaultdict
import os
import sys
import errno
import stat
import pyfuse3
import trio
import subprocess
import random

import faulthandler
faulthandler.enable()

import logging
logger_root = logging.getLogger(__name__)
dbglog = logger_root.getChild('debug')
acslog = logger_root.getChild('access')

import argparse

class TestFS(pyfuse3.Operations):

    enable_writeback_cache = False

    def __init__(self, path_source):
        super().__init__()
        self._inode_path_map = defaultdict(set)
        self._inode_fd_map = dict()
        self._inode_path_map[pyfuse3.ROOT_INODE].add(path_source)
        self._lookup_count = defaultdict(int)
        self._fd_open_count = defaultdict(int)
        self._fd_inode_map = dict()
        stat_source = os.lstat(path_source)
        self._src_device = stat_source.st_dev
        self.stat_path_open_r = set()
        self.stat_path_open_w = set()
        self.stat_path_open_rw = set()

    def _inode_to_path(self, inode):
        try:
            path_set = self._inode_path_map[inode]
        except KeyError:
            raise pyfuse3.FUSEError(errno.ENOENT)

        # FIXME: not good handling for hardlinks
        # inode_path_map entry may be invalid because parent dir was renamed.
        # We have to check it and clean up if file path is queryed.
        for p in path_set.copy():
            if not os.path.exists(p):
                path_set.remove(p)
                continue
            return p
        else:
            raise pyfuse3.FUSEError(errno.ENOENT)

    def _remember_path(self, inode, path):
        if inode == 1:
            dbglog.warn('remember_path called with invalid inode:{}, path:{}'.format(inode, path))
            return
        path_set = self._inode_path_map[inode]

        # if parent directory was renamed, existing entry may be invalid.
        # So we have to check.
        for p in path_set.copy():
            if not os.path.exists(p):
                path_set.remove(p)

        self._lookup_count[inode] += 1
        path_set.add(path)

    def _forget_path(self, inode, path):
        self._inode_path_map[inode].remove(path)
        if len(self._inode_path_map[inode]) == 0:
            del self._inode_path_map[inode]

    async def statfs(self, ctx):
        root = self._inode_to_path(pyfuse3.ROOT_INODE)
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
            
    async def getattr(self, inode, ctx=None):
        if inode in self._inode_fd_map:
            return self._getattr(fd=self._inode_fd_map[inode])
        else:
            return self._getattr(path=self._inode_to_path(inode))

    def _getattr(self, path=None, fd=None):
        assert fd is None or path is None
        assert not(fd is None and path is None)
        dbglog.debug('getatter path: {}, fd: {}'.format(path, fd))
        try:
            stat = os.lstat(path) if path else os.fstat(fd)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)


        entry = pyfuse3.EntryAttributes()
        # copy attrs from base FS.
        for attr in ('st_ino', 'st_mode', 'st_nlink', 'st_uid', 'st_gid',
                     'st_rdev', 'st_size', 'st_atime_ns', 'st_mtime_ns',
                     'st_ctime_ns'):
            setattr(entry, attr, getattr(stat, attr))
        entry.generation = 0
        entry.entry_timeout = 0
        entry.attr_timeout = 0
        entry.st_blksize = 512
        entry.st_blocks = ((entry.st_size+entry.st_blksize-1) // entry.st_blksize)

        # FIXME: fixed inode will be conflict another inode
        if entry.st_ino == 1:
            assert path != '/'
            entry.st_ino = random.randrange(2_000_000, 3_000_000) 

        return entry

    async def setattr(self, inode, attr, needs, fd, ctx):
        if fd is None:
            pofd = self._inode_to_path(inode)
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

        return await self.getattr(inode)

    async def getxattr(self, inode, name_encd, ctx):
        name = os.fsdecode(name_encd)
        path = self._inode_to_path(inode)
        try:
            return os.getxattr(path, name)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)

    async def setxattr(self, inode, name_enced, value_enced, ctx):
        name = os.fsdecode(name_enced)
        path = self._inode_to_path(inode)
        try:
            os.setxattr(path, name, value_enced)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)

    async def removexattr(self, inode, name_enced, ctx):
        name = os.fsdecode(name_enced)
        path = self._inode_to_path(inode)
        try:
            os.removexattr(path, name)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)

    async def listxattr(self, inode, ctx):
        path = self._inode_to_path(inode)
        try:
            xattrs = os.listxattr(path)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        return list(map(os.fsencode, xattrs))

    async def readlink(self, inode, ctx):
        path = self._inode_to_path(inode)
        try:
            target = os.readlink(path)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        return os.fsencode(target)

    async def forget(self, inode_list):
        for (inode, nlookup) in inode_list:
            if self._lookup_count[inode] > nlookup:
                self._lookup_count[inode] -= nlookup
                continue
            assert inode not in self._inode_fd_map
            del self._lookup_count[inode]
            try:
                del self._inode_path_map[inode]
            except KeyError: # may have been deleted
                pass

    async def lookup(self, inode_parent, name, ctx=None):
        name_dec = os.fsdecode(name)
        path = os.path.join(self._inode_to_path(inode_parent), name_dec)
        attr = self._getattr(path=path)
        dbglog.debug("lookup called with path: {}".format(path))
        if name_dec != '.' and name_dec != '..':
            self._remember_path(attr.st_ino, path)
        return attr

    async def opendir(self, inode, ctx):
        acslog.info('OPENDIR: {}'.format(self._inode_path_map[inode]))
        return inode

    async def readdir(self, inode, offset, token):
        path = self._inode_to_path(inode)
        entries = list()
        for name in os.listdir(path):
            if name == '.' or name == '..':
                continue
            attr = self._getattr(path=os.path.join(path, name))
            entries.append((attr.st_ino, name, attr))

        dbglog.debug('read %d entries, starting at %d', len(entries), offset)
        # FIXME: result is break if entries is changed between two calls to readdir()
        for (ino, name, attr) in sorted(entries):
            if ino <= offset:
                continue
            want_next_entry = pyfuse3.readdir_reply(token, os.fsencode(name), attr, ino)
            dbglog.debug('readdir called: {}'.format(os.path.join(path, name)))
            if not want_next_entry:
                break
            # Don't count up lookup_count if want_next_entry == False
            self._remember_path(ino, os.path.join(path, name))

    async def mkdir(self, inode_parent, name, mode, ctx):
        path = os.path.join(self._inode_to_path(inode_parent), os.fsdecode(name))
        try:
            os.mkdir(path, mode=(mode & ~ctx.umask))
            os.chown(path, ctx.uid, ctx.gid)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        attr = self._getattr(path=path)
        inode = attr.st_ino
        self._remember_path(inode, path)
        acslog.info('MKDIR: {}'.format(path))
        return attr

    async def rmdir(self, inode_parent, name, ctx):
        path = os.path.join(self._inode_to_path(inode_parent), os.fsdecode(name))
        try:
            attr = os.lstat(path)
            os.rmdir(path)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        inode = attr.st_ino
        if inode in self._lookup_count:
            self._forget_path(inode, path)
        acslog.info('RMDIR: {}'.format(path))

    async def open(self, inode, flags, ctx):
        if inode in self._inode_fd_map:
            fd = self._inode_fd_map[inode]
            self._fd_open_count[fd] += 1
            return pyfuse3.FileInfo(fh=fd)
        path = self._inode_to_path(inode)
        try:
            fd = os.open(path, flags)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        self._inode_fd_map[inode] = fd
        self._fd_inode_map[fd] = inode
        self._fd_open_count[fd] = 1

        # Record accessed files;
        if flags & os.O_RDWR:
            self.stat_path_open_rw.add(path)
        elif flags & os.O_WRONLY:
            self.stat_path_open_w.add(path)
        else:
            self.stat_path_open_r.add(path)

        acslog.info('OPEN: {}'.format(path))
        return pyfuse3.FileInfo(fh=fd)

    async def read(self, fd, offset, length):
        os.lseek(fd, offset, os.SEEK_SET)
        acslog.info('READ: {}'.format(self._inode_path_map[self._fd_inode_map[fd]]))
        return os.read(fd, length)

    async def create(self, inode_parent, name, mode, flags, ctx):
        path = os.path.join(self._inode_to_path(inode_parent), os.fsdecode(name))
        try:
            fd = os.open(path, flags | os.O_CREAT | os.O_TRUNC, mode)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        attr = self._getattr(fd=fd)
        inode = attr.st_ino
        self._remember_path(inode, path)
        self._inode_fd_map[inode] = fd
        self._fd_inode_map[fd] = inode
        self._fd_open_count[fd] = 1
        acslog.info('CREATE: {}'.format(path))
        return pyfuse3.FileInfo(fh=fd), attr

    async def write(self, fd, offset, buf):
        os.lseek(fd, offset, os.SEEK_SET)
        acslog.info('WRITE: {}'.format(self._inode_path_map[self._fd_inode_map[fd]]))
        return os.write(fd, buf)

    async def release(self, fd):
        if self._fd_open_count[fd] > 1:
            self._fd_open_count[fd] -= 1
            return

        assert self._fd_open_count[fd] == 1
        del self._fd_open_count[fd]
        inode = self._fd_inode_map[fd]
        del self._inode_fd_map[inode]
        del self._fd_inode_map[fd]
        acslog.info('')
        try:
            os.close(fd)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)

    async def rename(self, inode_old_parent, name_old_enced, inode_new_parent, name_new_enced, flags, ctx):
        name_old = os.fsdecode(name_old_enced)
        name_new = os.fsdecode(name_new_enced)
        parent_old = self._inode_to_path(inode_old_parent)
        parent_new = self._inode_to_path(inode_new_parent)
        path_old = os.path.join(parent_old, name_old)
        path_new = os.path.join(parent_new, name_new)
        try:
            os.rename(path_old, path_new)
            inode = os.lstat(path_new).st_ino
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)

        acslog.info('RENAME: {} -> {}'.format(path_old, path_new))

        if inode not in self._inode_path_map:
            return
        # don't increase / decrease lookup count
        self._inode_path_map[inode].add(path_new)
        self._inode_path_map[inode].remove(path_old)

    async def link(self, inode, new_inode_parent, new_name_enced, ctx):
        new_name = os.fsdecode(new_name_enced)
        parent = self._inode_to_path(new_inode_parent)
        path = os.path.join(parent, new_name)
        try:
            os.link(self._inode_to_path(inode), path, follow_symlinks=False)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        self._remember_path(inode, path)
        acslog.info('LINK: {}'.format(path))
        return await self.getattr(inode)

    async def unlink(self, inode_parent, name_enced, ctx):
        name = os.fsdecode(name_enced)
        parent = self._inode_to_path(inode_parent)
        path = os.path.join(parent, name)
        try:
            inode = os.lstat(path).st_ino
            os.unlink(path)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        if inode in self._inode_path_map:
            self._forget_path(inode, path)
        acslog.info('UNLINK: {}'.format(path))

    async def symlink(self, inode_parent, source_enced, target_enced, ctx):
        source = os.fsdecode(source_enced)
        target = os.fsdecode(target_enced)
        parent = self._inode_to_path(inode_parent)
        path = os.path.join(parent, source)
        try:
            os.symlink(target, path)
            os.chown(path, ctx.uid, ctx.gid, follow_symlinks=False)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        stat = os.lstat(path)
        self._remember_path(stat.st_ino, path)
        return await self.getattr(stat.st_ino)


async def mount_pseudo_fs(mountpoint):
    await trio.sleep(2)
    dbglog.debug('mount pseudo fs')
    p_proc = subprocess.Popen(['/bin/mount', '-t', 'proc', 'proc', '{}/proc'.format(mountpoint)])
    p_sys = subprocess.Popen(['/bin/mount', '-t', 'sysfs', 'sys', '{}/sys'.format(mountpoint)])
    p_dev = subprocess.Popen(['/bin/mount', '--rbind', '/dev', '{}/dev'.format(mountpoint)])
    p_proc.wait()
    p_sys.wait()
    dbglog.debug('complete mount pseudo fs')

async def start(mountpoint):
    async with trio.open_nursery() as nursery:
        nursery.start_soon(pyfuse3.main)
        #nursery.start_soon(mount_pseudo_fs, mountpoint)

def export_logfile(fs, basepath):
    import csv
    o_r = sorted(list(fs.stat_path_open_r))
    o_w = sorted(list(fs.stat_path_open_w))
    o_rw = sorted(list(fs.stat_path_open_rw))
    with open(basepath + '.r.txt', mode='w', newline='') as fd:
        csv.writer(fd, delimiter='\n').writerow(o_r)
    with open(basepath + '.w.txt', mode='w', newline='') as fd:
        csv.writer(fd, delimiter='\n').writerows(o_w)
    with open(basepath + '.rw.txt', mode='w', newline='') as fd:
        csv.writer(fd, delimiter='\n').writerows(o_rw)

def main():
    ### parse command line ###
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=str)
    parser.add_argument('mountpoint', type=str)
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--logfile', type=str)
    args = parser.parse_args()

    ### initialize logger ###
    dbglogformatter = logging.Formatter()
    dbgloghandler = logging.StreamHandler()
    dbgloghandler.setFormatter(dbglogformatter)
    dbglog.addHandler(dbgloghandler)
    if args.debug:
        dbglog.setLevel(logging.DEBUG)
    else:
        dbglog.setLevel(logging.INFO)
    acslog.setLevel(logging.INFO)
    acsformatter = logging.Formatter()
    acshandler = logging.StreamHandler(sys.stdout)
    acshandler.setFormatter(acsformatter)
    acslog.addHandler(acshandler)

    ### start filesystem ###
    testfs = TestFS(args.source)
    fuse_options = set(pyfuse3.default_options)
    fuse_options.add('fsname=testfs')
    if args.debug:
        fuse_options.add('debug')
    fuse_options.add('dev')
    pyfuse3.init(testfs, args.mountpoint, fuse_options)
    try:
        #trio.run(pyfuse3.main)
        trio.run(start, args.mountpoint)
    finally:
        pyfuse3.close(unmount=True)

    if args.logfile:
        export_logfile(testfs, args.logfile)

    sys.exit(0)


if __name__ == '__main__':
    main()
