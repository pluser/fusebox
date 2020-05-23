#!/usr/bin/python3
# -*- coding: utf-8 -*-
'''
fusebox.py - Entry point of FUSE-powered sandbox system
'''

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
    def __init__(self):
        super().__init__()
        self.hello_name = b"message"
        self.hello_inode = pyfuse3.ROOT_INODE+1
        self.hello_data = b"hello world\n"

    async def getattr(self, inode, ctx=None):
        entry = pyfuse3.EntryAttributes()
        if inode == pyfuse3.ROOT_INODE:
            entry.st_mode = (stat.S_IFDIR | 0o755)
            entry.st_size = 0
        elif inode == self.hello_inode:
            entry.st_mode = (stat.S_IFREG | 0o644)
            entry.st_size = len(self.hello_data)
        else:
            raise pyfuse3.FUSEError(errnr.ENOENT)

        stamp = int(1438467123.985654 * 1e9)
        entry.st_atime_ns = stamp
        entry.st_ctime_ns = stamp
        entry.st_mtime_ns = stamp
        entry.st_gid = os.getgid()
        entry.st_uid = os.getuid()
        entry.st_ino = inode

        return entry

    async def lookup(self, parent_inode, name, ctx=None):
        if parent_inode != pyfuse3.ROOT_INODE or name != self.hello_name:
            raise pyfuse.FUSEError(errno.ENOENT)
        return self.getattr(self.hello_inode)

    async def opendir(self, inode, ctx):
        if inode != pyfuse3.ROOT_INODE:
            raise pyfuse3.FUSEError(errno.ENOENT)
        return inode

    async def readdir(self, fh, start_id, token):
        assert fh == pyfuse3.ROOT_INODE

        if start_id == 0:
            pyfuse3.readdir_reply(token, self.hello_name, await self.getattr(self.hello_inode), 1)

        return

def main():
    ### parse command line ###
    parser = argparse.ArgumentParser()
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
    testfs = TestFS()
    fuse_options = set(pyfuse3.default_options)
    fuse_options.add('fsname=testfs')
    fuse_options.add('debug')
    pyfuse3.init(TestFS(), args.mountpoint, fuse_options)
    try:
        trio.run(pyfuse3.main)
    except:
        pyfuse3.close(unmount=False)
        raise RuntimeError

    pyfuse3.close()


if __name__ == '__main__':
    main()
