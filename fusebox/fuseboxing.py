#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
fusebox-sandbox.py - Entry point of FUSE-powered sandbox system
"""

import os
import sys
import argparse
import logging
import subprocess
import multiprocessing
import trio
import pyfuse3
from . import fusefs

logger_root = logging.getLogger('Fusebox')
dbglog = logger_root.getChild('operation')
acslog = logger_root.getChild('access')
MOUNTPOINT = '/tmp/test'

def launcher(cmd):
    curwd = os.getcwd()
    os.chroot(MOUNTPOINT)  # now, process is in the jail
    os.chdir(curwd)  # go to the working directory on sandbox
    subprocess.run(cmd)

def main():
    ### parse command line ###
    parser = argparse.ArgumentParser()
    parser.add_argument('--fusebox_debug')
    args, cmd = parser.parse_known_args()
    # sometimes cmd is taken as blob of args string
    # i.e. cmd = ['/usr/lib/portage/python3.7/misc-functions.sh die_hooks']
    # if so, split it.
    if len(cmd) == 1:
        cmd = list(cmd[0].split())

    ### initialize logger ###
    dbglogformatter = logging.Formatter()
    dbgloghandler = logging.StreamHandler()
    dbgloghandler.setFormatter(dbglogformatter)
    dbglog.addHandler(dbgloghandler)
    if args.fusebox_debug:
        dbglog.setLevel(logging.DEBUG)
    else:
        dbglog.setLevel(logging.INFO)
    acslog.setLevel(logging.INFO)
    acsformatter = logging.Formatter()
    acshandler = logging.StreamHandler(sys.stdout)
    acshandler.setFormatter(acsformatter)
    acslog.addHandler(acshandler)

    # start filesystem ###
    fsops = fusefs.Fusebox(os.path.abspath('/'), os.path.abspath(MOUNTPOINT))
    fuse_options = set(pyfuse3.default_options)
    fuse_options.add('fsname=fusefs')
    if args.fusebox_debug:
        fuse_options.add('debug')
    fuse_options.add('dev')
    pyfuse3.init(fsops, MOUNTPOINT, fuse_options)
    fsops.auditor.allowread('/')  # FIXME: allow all access to test...
    fsops.auditor.allowwrite('/')  # FIXME: allow all access to test...

    proc = multiprocessing.Process(target=launcher, args=(cmd,))
    print(cmd)
    proc.start()
    try:
        trio.run(pyfuse3.main)
    finally:
        pyfuse3.close(unmount=True)
    proc.join()  # to eliminate zombie process


if __name__ == '__main__':
    main()
