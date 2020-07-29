# Fusebox - A new sandbox implemented with FUSE (Filesystem in Userspace)

## What is this

Fusebox is new implementation of sandbox for Portage (package system for Gentoo Project).

The sandbox currently used in the Portage package system hooks up writes to the file system by using LD_PRELOAD, but this method has a few drawbacks.  This project develops a new sandbox mechanism based on FUSE, while maintaining compatibility.

## Requirements
- kernel FUSE support CONFIG_FUSE_FS
- sys-fs/fuse `emerge sys-fs/fuse`
- pyfuse `pip install pyfuse3`

## How to Use

1. Mount rootfs to arbitary mountpoint.
`python fusebox.py / ${MOUNTPOINT}`
1. In another terminal, mount pseudo filesystems
   - `mount -t proc procfs ${MOUNTPOINT}/proc`
   - `mount -t sysfs sysfs ${MOUNTPOINT}/sys`
   - `mount --rbind /dev ${MOUNTPOINT}/dev`
   - `mount --make-rslave ${MOUNTPOINT}/dev`
   - `mount -t tmpfs tmpfs ${MOUNTPOINT}/tmp`
1. chroot to that directory
`chroot ${MOUNTPOINT} /bin/bash`
1. Download GNU hello
`curl -O http://ftp.gnu.org/gnu/hello/hello-2.10.tar.gz`
1. Extract gzip file
`tar xvf hello-2.10.tar.gz`
1. cd and make binary (and install?)
   - `cd hello-2.10`
   - `./configure`
   - `make`
   - `make install`
1. Clean up
   - `umount -l ${MOUNTPOINT}/{proc,sys,dev,tmp}`
   - `fusermount -u ${MOUNTPOINT}` 

## Features
### Access Control
1. In default, Accessing any file is prohibited.
```cat: /mnt/fusebox/etc/os-release: Permission denied```
1. To give permission, you can write pseudo file as `fuseboxctlv1` in the mountpoint.
   Syntax is like below.
   ```
   allowread /etc/os-release (same as addread)
   allowwrite /etc/os-release
   denyread /etc/os-release
   denywrite /etc/os-release
   
   # for the compatible
   addread /etc/os-release
   addwrite /etc/os-release (same as allowread + allowwrite)
   adddeny /etc/os-release (same as denyread + denywrite)
   ```
   (FYI: If you want to chroot, please grant permission to /bin, /usr, /etc, /lib64)

### Export to logfile
1. Please use logfile option.
`python fusebox.py --logfile=foobar / ${MOUNTPOINT}`
Fusebox exports three files `foobar.r.txt`, `foobar.w.txt`, `foobar.rw.txt` if mountpoint is unmounted gracefully.
It contains list of files which was opend as each mode.
The list is sorted and doesn't have duplicate.
