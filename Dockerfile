# syntax=docker/dockerfile:experimental
FROM gentoo/portage:latest AS portage
FROM gentoo/stage3-amd64:latest

COPY --from=portage /var/db/repos/gentoo /var/db/repos/gentoo
VOLUME ["/fusebox", "/var/cache/binpkgs", "/var/cache/distfiles"]

RUN --mount=type=cache,target=/var/cache/binpkgs --mount=type=cache,target=/var/cache/distfiles --mount=type=cache,target=/root/.cache/pip \
echo -e 'dev-python/pip vanilla\ndev-vcs/git -perl' >> /etc/portage/package.use/base.conf && \
FEATURES='-usersandbox' emerge --noreplace --quiet --buildpkg --usepkg dev-lang/python:{3.6,3.7,3.8} dev-python/pypy3 dev-python/pypy3-exe-bin sys-fs/fuse dev-python/pip dev-vcs/git && \
pip install poetry pyfuse3 tox

CMD ["/bin/bash"]
