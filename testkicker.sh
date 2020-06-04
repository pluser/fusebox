#!/bin/bash -x

cd /fusebox
poetry install
poetry run python fusebox.py --help
