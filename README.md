# Fusebox - A new sandbox implemented with FUSE (Filesystem in Userspace)

## What is this ##

Fusebox is new implementation of sandbox for Portage (package system for Gentoo Project).

The sandbox currently used in the Portage package system hooks up writes to the file system by using LD_PRELOAD, but this method has a few drawbacks.  This project develops a new sandbox mechanism based on FUSE, while maintaining compatibility.

**Caveats**: Fusebox is not secure sandbox. Fusebox is not designed to protect your system from suspicious behavior, such as malware.

## Features ##

- Paththrough all access to another filesystem. like bind mount.
- Access Control. Traps file access and check it, then stop it when access is not permitted.
- Convinient permission list management. You can simply update the ACL by reading and writing special file.
- Fooling the process. Traps writing to a file and pretends to be written to.

## Requirements ##

- Linux Kernel FUSE support `CONFIG_FUSE_FS`
- sys-fs/fuse `emerge sys-fs/fuse`
- pyfuse3 `pip install pyfuse3`

## How to Use ##

1.	Start fusebox with arbitary program. `python -m fusebox.fuseboxing /bin/bash`

1.	In default, access control feature is disabled.
	```
	*** Fusebox Status ***
	uid:	0
	gid:	0
	pid:	127607
	prev_umask:		0022
	cmd:	['/bin/bash']
	acl:	disengaged
	mount:	/tmp/tmp5k7xrkes
	@@@ Fusebox Launched in fuseboxing.py @@@
	```

	to make access control feature enable, `echo 1 > /fuseboxctlv1/acl_switch`, and  
	to make access control feature disable, `echo 0 > /fuseboxctlv1/acl_switch`.  
	You can read the file to check whether access control feature is on/off with `cat /fuseboxctlv1/acl_switch`.

1.	To grant access, you can write pseudo file as `/fuseboxctlv1/acl` in the mountpoint.  
	Syntax is like below.

	```
	allowread /etc
	allowwrite /etc
	denyread /etc
	denywrite /etc
	discardwrite /etc

	# for the compatibility
	addread /etc (same as allowread)
	addwrite /etc  (same as allowread + allowwrite)
	adddeny /etc  (same as denyread + denywrite)
	addpredict /etc  (same as allowread + discardwrite)
	```

	For example,

	```
	# echo addread / >> /fuseboxctlv1/acl
	Permitted reading from path </>.
	# echo denywrite /usr >> /fuseboxctlv1/acl
	Prohibited writing to path </usr>.
	```

	Also, you can read current ACL from the file.

	```
	$ cat /fuseboxctlv1/acl
	# Don't remove a next line
	clearall
	
	allowread /
	denywrite /usr
	```

1.	To integrate with portage, please apply the patch to the Portage.

	```
	patch -p1 < patch/portage-2.3.103.patch
	```

	or, please replace files in `patch/`.

	```
	# cp patch/ebuild.sh /usr/lib/portage/python3.7/ebuild.sh
	# cp patch/phase-functions.sh /usr/lib/portage/python3.7/phase-functions.sh
	```

1.	cd to ebuild directory and try to start ebuild phases.

	```
	# cd /var/db/repos/gentoo/app-misc/hello
	# ebuild hello-2.10-r1.ebuild install
	```

1.	Exit main program will cause automatically closing Fusebox mount.

	```
	# exit
	```

## ToDo
1.	Further integration with emerge tool.

	Currently, Fusebox can run whole ebuild process (unpack, configure, compile, install...).
	However, The goal is integrate with 'emerge' program. When combined with the emerge tool, it does not work well and the cause needs to be explored. (There may be a problem with IPC.)

1.	Compatibility.

	For now, the program has been targeting a fairly simple package, GNU hello (app-misc/hello).
	Due to a lack of testing, it may not work well for very complex packages. It needs to be tested in more packages.

1.	Support for pseudo file systems.

	Currently, Fusebox does not handle access to virtual file systems such as /dev and /proc well.
	As a result, access to these requires additional mounts internally and is an exception to the ACL.

## For Developer
### File Structure
	. - Project root.
	├── fusebox/ - All source code is here.
	│   ├── __init__.py
	│   ├── auditor.py - Access control related code.
	│   ├── fusebox.py - Program entry point (may be deplicated).
	│   ├── fuseboxing.py - Program entry point. Parse arguments, invoke FUSE process, start specified program.
	│   ├── fusefs.py - FUSE related code. Implementing filesystem.
	│   ├── pseudo.py - Treat special file like Fusebox control files (/fuseboxctlv1/acl, etc).
	│   └── vnode.py - Virtual inode. Map the sandboxed files to the actual files.
	├── patch/ - Explained above. Including the patches needed to integrate with portage.
	├── pyproject.toml - Project settings.
	├── setup.py - Project settings which is generated from pyproject.toml, but It's placed there because it's convenient.
	├── testkicker.sh - Used by test on CI.
	├── tests/ - All test code is here.
	└── tox.ini