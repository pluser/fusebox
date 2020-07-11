#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
fusebox.py - Entry point of FUSE-powered sandbox system
"""

import sys
import pyfuse3
import trio
import argparse
import logging
import fusefs

logger_root = logging.getLogger('Fusebox')
dbglog = logger_root.getChild('debug')
acslog = logger_root.getChild('access')


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
    # parse command line ###
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=str)
    parser.add_argument('mountpoint', type=str)
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--logfile', type=str)
    args = parser.parse_args()

    # initialize logger ###
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

    # start filesystem ###
    fsops = fusefs.Fusebox(args.source, args.mountpoint)
    fuse_options = set(pyfuse3.default_options)
    fuse_options.add('fsname=testfs')
    if args.debug:
        fuse_options.add('debug')
    fuse_options.add('dev')
    pyfuse3.init(fsops, args.mountpoint, fuse_options)
    try:
        trio.run(pyfuse3.main)
    finally:
        pyfuse3.close(unmount=True)

    if args.logfile:
        export_logfile(fsops, args.logfile)

    sys.exit(0)


if __name__ == '__main__':
    main()
