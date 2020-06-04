#!/bin/bash -x

echo '*** Installing system packages/modules etc...'
echo -e 'dev-python/pip vanilla\ndev-vcs/git -perl' >> /etc/portage/package.use/base.conf
emerge --quiet --buildpkg --usepkg sys-fs/fuse dev-python/pip dev-vcs/git
pip install poetry
echo '*** Installing is done.'

cd /fusebox
echo '*** Installing project specific packages.'
poetry install
echo '*** Installing is done.'
echo '*** Start testing...'
poetry run python fusebox.py --help
