#!/bin/bash -x

echo '*** Installing system packages/modules etc...'
FEATURES='-usersandbox' emerge --noreplace --quiet --buildpkg --usepkg dev-lang/python:{3.6,3.7,3.8} dev-python/pypy3 sys-fs/fuse dev-python/pip dev-vcs/git
pip install poetry pyfuse3 tox
echo '*** Installing is done.'

cd /fusebox
echo '*** Installing project specific packages.'
poetry install
echo '*** Installing is done.'
echo '*** Start testing...'
poetry run python fusebox.py --help
poetry run tox
