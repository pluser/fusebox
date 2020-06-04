FROM gentoo/portage:latest AS portage
FROM gentoo/stage3-amd64:latest

COPY --from=portage /var/db/repos/gentoo /var/db/repos/gentoo
VOLUME ["/fusebox"]

RUN \
echo -e 'dev-python/pip vanilla\ndev-vcs/git -perl' >> /etc/portage/package.use/base.conf && \
emerge --quiet sys-fs/fuse dev-python/pip dev-vcs/git && \
pip install poetry
	   
CMD ["/bin/bash"]