FROM gentoo/portage:latest AS portage
FROM gentoo/stage3-amd64:latest

COPY --from=portage /var/db/repos/gentoo /var/db/repos/gentoo
VOLUME ["/fusebox", "/var/cache/binpkgs", "/var/cache/distfiles"]
	   
CMD ["/bin/bash"]