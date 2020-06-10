#!/usr/bin/python3
# -*- coding: utf-8 -*-
'''
fusebox.py - Entry point of FUSE-powered sandbox system
'''

from collections import defaultdict
import os
import sys
import stat
import pyfuse3
import trio

import faulthandler
faulthandler.enable()

import logging
logger = logging.getLogger(__name__)

import argparse

class TestFS(pyfuse3.Operations):
    def __init__(self, path_source):
        super().__init__()
        self._inode_path_map = defaultdict(set)
        self._inode_fd_map = dict()
        self._inode_path_map[pyfuse3.ROOT_INODE].add(path_source)
        self._lookup_count = defaultdict(int)
        self._fd_open_count = defaultdict(int)
        self._fd_inode_map = dict()

    def _inode_to_path(self, inode):
        if inode in self._inode_path_map:
            path_set = self._inode_path_map[inode]
        else:
            raise pyfuse3.FUSEError(errno.ENOENT)

        path = next(iter(path_set)) # FIXME: not good handling for hardlinks
        return path

    def _remember_path(self, inode, path):
        self._lookup_count[inode] += 1
        self._inode_path_map[inode].add(path)
        return

    def _forget_path(self, inode, path):
        self._inode_path_map[inode].remove(path)
        if self._inode_path_map[inode]:
            del self._inode_path_map[inode]
            
    async def getattr(self, inode, ctx=None):
        if inode in self._inode_fd_map:
            return self._getattr(fd=self._inode_fd_map[inode])
        else:
            return self._getattr(path=self._inode_to_path(inode))

    def _getattr(self, path=None, fd=None):
        assert fd is None or path is None
        assert not(fd is None and path is None)

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

        return entry

    async def lookup(self, inode_parent, name, ctx=None):
        name_dec = os.fsdecode(name)
        path = os.path.join(self._inode_to_path(inode_parent), name_dec)
        attr = self._getattr(path=path)
        if name_dec != '.' and name_dec != '..':
            self._remember_path(attr.st_ino, path)
        return attr

    async def opendir(self, inode, ctx):
        return inode

    async def readdir(self, inode, offset, token):
        path = self._inode_to_path(inode)
        entries = list()
        for name in os.listdir(path):
            if name == '.' or name == '..':
                continue
            attr = self._getattr(path=os.path.join(path, name))
            entries.append((attr.st_ino, name, attr))

        # FIXME: result is break if entries is changed between two calls to readdir()
        for (ino, name, attr) in sorted(entries):
            if ino <= offset:
                continue
            if not pyfuse3.readdir_reply(token, os.fsencode(name), attr, ino):
                break
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

    async def open(self, inode, flags, ctx):
        if inode in self._inode_fd_map:
            self._fd_open_count[fd] += 1
            return pyfuse3.FileInfo(fh=fd)
        try:
            fd = os.open(self._inode_to_path(inode), flags)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        self._inode_fd_map[inode] = fd
        self._fd_inode_map[fd] = inode
        self._fd_open_count[fd] = 1
        return pyfuse3.FileInfo(fh=fd)

    async def read(self, fd, offset, length):
        os.lseek(fd, offset, os.SEEK_SET)
        return os.read(fd, length)

    async def create(self, inode_parent, name, mode, flags, ctx):
        path = os.path.join(self._inode_to_path(inode_parent), os.fsdecode(name))
        try:
            fd = os.open(path, flags | os.O_CREAT | os.O_TRUNC)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
        attr = self._getattr(fd=fd)
        inode = attr.st_ino
        self._remember_path(inode, path)
        self._inode_fd_map[inode] = fd
        self._fd_inode_map[fd] = inode
        self._fd_open_count[fd] = 1
        return pyfuse3.FileInfo(fh=fd), attr

    async def write(self, fd, offset, buf):
        os.lseek(fd, offset, os.SEEK_SET)
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
        try:
            os.close(fd)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)
def main():
    ### parse command line ###
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=str)
    parser.add_argument('mountpoint', type=str)
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    ### initialize logger ###
    formatter = logging.Formatter('%(asctime)s.%(msecs)03d %(threadName)s: '
                                  '[%(name)s] %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    if args.debug:
        handler.setLevel(logging.DEBUG)
        root_logger.setLevel(logging.DEBUG)
    else:
        handler.setLevel(logging.INFO)
        root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    ### start filesystem ###
    testfs = TestFS(args.source)
    fuse_options = set(pyfuse3.default_options)
    fuse_options.add('fsname=testfs')
    fuse_options.add('debug')
    pyfuse3.init(testfs, args.mountpoint, fuse_options)
    try:
        trio.run(pyfuse3.main)
    except:
        pyfuse3.close(unmount=False)
        raise RuntimeError

    pyfuse3.close()


if __name__ == '__main__':
    main()
