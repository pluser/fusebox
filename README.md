# Fusebox - A new sandbox implemented with FUSE (Filesystem in Userspace)

## What is this

Fusebox is new implementation of sandbox for Portage (package system for Gentoo Project).

The sandbox currently used in the Portage package system hooks up writes to the file system by using LD_PRELOAD, but this method has a few drawbacks.  This project develops a new sandbox mechanism based on FUSE, while maintaining compatibility.

## Requirements
- kernel FUSE support CONFIG_FUSE_FS
- sys-fs/fuse `emerge sys-fs/fuse`
- pyfuse `pip install pyfuse3`

## How to Use

1. Start fusebox with arbitary program.
`python -m fusebox.fuseboxing /bin/bash`

1. In default, ACL feature is disabled.
    ```
    *** Fusebox Status ***
    uid:    0
    gid:    0
    pid:    127607
    prev_umask:     0022
    cmd:    ['/bin/bash']
    acl:    disengaged
    mount:  /tmp/tmp5k7xrkes
    @@@ Fusebox Launched in fuseboxing.py @@@
    ```

   to make enable, `echo 1 > /fuseboxctlv1/acl_switch`, and
   to make disable, `echo 0 > /fuseboxctlv1/acl_switch`.
   You can read the file to sense whether ACL feature is on/off with `cat /fuseboxctlv1/acl_switch`.

   Also, ACL is readable/writable.
   ```
   # echo addread / >> /fuseboxctlv1/acl
   Permitted reading from path </>.
   # echo denywrite /usr >> /fuseboxctlv1/acl
   Prohibited writing to path </usr>.
   cat /fuseboxctlv1/acl
   # Don't remove a next line
   clearall
   
   allowread /
   denywrite /usr
   ```

1. To integrate with portage, please replace files in `patch/`.
    ```
    # cp patch/ebuild.sh /usr/lib/portage/python3.7/ebuild.sh
    # cp patch/phase-functions.sh /usr/lib/portage/python3.7/phase-functions.sh
    ```

1. cd to ebuild directory and try to start ebuild phases.
    ```
    # cd /var/db/repos/gentoo/app-misc/hello
    # ebuild hello-2.10-r1.ebuild install
    ```

1. Exit main program will cause automatically closing Fusebox mount.
    ```
    # exit
    ```

## Features
### Access Control
1. In default, Accessing any file is prohibited.
```cat: /mnt/fusebox/etc/os-release: Permission denied```
1. To give permission, you can write pseudo file as `fuseboxctlv1` in the mountpoint.
   Syntax is like below.
   ```
   allowread /etc/os-release
   allowwrite /etc/os-release
   denyread /etc/os-release
   denywrite /etc/os-release
   discardwrite /etc/os-release
   
   # for the compatible
   addread /etc/os-release (same as allowread)
   addwrite /etc/os-release (same as allowread + allowwrite)
   adddeny /etc/os-release (same as denyread + denywrite)
   addpredict /etc/os-release (same as allowread + discardwrite)
   ```
   (FYI: If you want to chroot, please grant permission to /bin, /usr, /etc, /lib64)

### Export to logfile
1. Please use logfile option.
`python fusebox.py --logfile=foobar / ${MOUNTPOINT}`
Fusebox exports three files `foobar.r.txt`, `foobar.w.txt`, `foobar.rw.txt` if mountpoint is unmounted gracefully.
It contains list of files which was opend as each mode.
The list is sorted and doesn't have duplicate.
