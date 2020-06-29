# Fusebox - A new sandbox implemented with FUSE (Filesystem in Userspace)

## What is this

Fusebox is new implementation of sandbox for Portage (package system for Gentoo Project).

The sandbox currently used in the Portage package system hooks up writes to the file system by using LD_PRELOAD, but this method has a few drawbacks.  This project develops a new sandbox mechanism based on FUSE, while maintaining compatibility.

## Requirments
- kernel fuse support CONFIG_FUSE_FS
- sys-fs/fuse `emerge sys-fs/fuse`
- pyfuse `pip install pyfuse3`

## How to Use

1. Mount rootfs to arbitary mountpoint.
`python fusebox.py --debug / /tmp/arbitary_mp`
1. In another terminal, chroot to that directory
`chroot /tmp/arbitary_mp /bin/bash`
1. Download GNU hello
`curl -O http://ftp.gnu.org/gnu/hello/hello-2.10.tar.gz`
1. Extract gzip file
`tar xvf hello-2.10.tar.gz`
1. cd and make binary (and install?)
`cd hello`
`./configure`
`make`
`make install`
