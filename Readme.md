# FUSEbox - A new sandbox implemented with FUSE (Filesystem in Userspace)

## What is this

FUSEbox is new implementation of sandbox for Portage (package system for Gentoo Project).

The sandbox currently used in the Portage package system hooks up writes to the file system by using LD_PRELOAD, but this method has a few drawbacks.  This project develops a new sandbox mechanism based on FUSE, while maintaining compatibility.

## How to Use

1. Mount rootfs to arbitary mountpoint.
`python fusebox.py --debug / /tmp/arbitary_mp`
1. chroot to that point
`chroot /tmp/arbitary_mp /bin/bash`
1. run emerge
`emerge -a something`
