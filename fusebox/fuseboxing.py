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

def launcher(cmd, pipe_stdin):
    curwd = os.getcwd()
    subprocess.run(['mount', '--types', 'proc', '/proc', MOUNTPOINT+'/proc'])
    subprocess.run(['mount', '--rbind', '/sys', MOUNTPOINT+'/sys'])
    subprocess.run(['mount', '--make-rslave', MOUNTPOINT+'/sys'])
    subprocess.run(['mount', '--rbind', '/dev', MOUNTPOINT+'/dev'])
    subprocess.run(['mount', '--make-rslave', MOUNTPOINT+'/dev'])
    os.chroot(MOUNTPOINT)  # now, process is in the jail
    os.chdir(curwd)  # go to the working directory on sandbox
    print('@@@ Fusebox Launched in fuseboxing.py @@@')
    # FIXME: shuld be respect uid and gid
    # which should be given from emerge process
    #print(os.read(pipe_stdin, 7))
    #cmd.insert(0, '/usr/bin/sandbox')
    #print(cmd)
    #os.dup2(pipe_stdin, sys.stdin.fileno())
    #os.dup2(pipe_stdin, 0)
    #print(sys.stdin.fileno())
    #sys.stdin = os.fdopen(0, 'r')
    proc = subprocess.Popen(cmd, stdin=pipe_stdin)
    #proc.communicate()
    #proc.communicate()
    #print(proc.stdin.fileno())
    #os.dup2(pipe_stdin, proc.stdin.fileno())
    #os.write(proc.stdin.fileno(), b'abcd')
    proc.wait()

def start_sandbox():
    try:
        trio.run(pyfuse3.main)
    finally:
        pyfuse3.close(unmount=True)

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
    dbglog.setLevel(logging.INFO)
    acslog.setLevel(logging.WARNING)
    acsformatter = logging.Formatter()
    acshandler = logging.StreamHandler(sys.stdout)
    acshandler.setFormatter(acsformatter)
    acslog.addHandler(acshandler)

    # setting process environment
    umask_prev = os.umask(0)  # to respect file permission which user specified

    # print current status
    dbglog.info('*** Fusebox Status ***')
    dbglog.info('uid:\t{}'.format(os.getuid()))
    dbglog.info('gid:\t{}'.format(os.getgid()))
    dbglog.info('pid:\t{}'.format(os.getpid()))
    dbglog.info('prev_umask:\t{:04o}'.format(umask_prev))

    # start filesystem ###
    fsops = fusefs.Fusebox(os.path.abspath('/'), os.path.abspath(MOUNTPOINT))
    fuse_options = set(pyfuse3.default_options)
    fuse_options.add('fsname=fusefs')
    if args.fusebox_debug:
        fuse_options.add('debug')
    fuse_options.add('dev')
    fuse_options.add('allow_other')
    pyfuse3.init(fsops, MOUNTPOINT, fuse_options)  # From this point, accessing under mountpoint will be blocked.
    fsops.auditor.allowread('/')  # FIXME: allow all access to test...
    fsops.auditor.allowwrite('/')  # FIXME: allow all access to test...

    #pipe_reciver, pipe_sender = os.pipe()
    #os.set_inheritable(pipe_reciver, True)
    tmp_stdin = os.dup(sys.stdin.fileno())  # backup stdin fd. since multiprocessing will override stdin in forked process.
    os.set_inheritable(tmp_stdin, True)  # make sure to keep fd opened in forked process.
    proc_cmd = multiprocessing.Process(target=launcher, args=(cmd, tmp_stdin))
    proc_fusebox = multiprocessing.Process(target=start_sandbox)
    del tmp_stdin  # forget backuped pipe in parent process as it is not needed.
    proc_cmd.start()
    proc_fusebox.start()
    #os.write(pipe_sender, b'1234\n')
    #os.close(pipe_sender)
    #print('sended')

    proc_cmd.join()  # to eliminate zombie process
    proc_fusebox.join()


if __name__ == '__main__':
    main()
