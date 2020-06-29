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
`python fusebox.py / ${MOUNTPOINT}`
1. In another terminal, mount pseudo filesystems
`mount -t proc procfs ${MOUNTPOINT}/proc`
`mount -t sysfs sysfs ${MOUNTPOINT}/sys`
`mount --rbind /dev ${MOUNTPOINT}/dev`
`mount --make-rslave ${MOUNTPOINT}/dev`
`mount -t tmpfs tmpfs ${MOUNTPOINT}/tmp`
1. chroot to that directory
`chroot /tmp/${MOUNTPOINT} /bin/bash`
1. Download GNU hello
`curl -O http://ftp.gnu.org/gnu/hello/hello-2.10.tar.gz`
1. Extract gzip file
`tar xvf hello-2.10.tar.gz`
1. cd and make binary (and install?)
`cd hello-2.10`
`./configure`
`make`
`make install`
1. cleanup
`umount -l ${MOUNTPOINT}/{proc,sys,dev,tmp}`
`fusemount ${MOUNTPOINT}` 
