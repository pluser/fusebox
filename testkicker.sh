#!/bin/bash -x

echo '*** Installing system packages/modules etc...'
emerge --noreplace --quiet --buildpkg --usepkg sys-fs/fuse dev-python/pip dev-vcs/git
pip install poetry
echo '*** Installing is done.'

cd /fusebox
echo '*** Installing project specific packages.'
poetry install
echo '*** Installing is done.'
echo '*** Start testing...'
poetry run python fusebox.py --help
pertry run python -m pytest
