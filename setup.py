# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['fusebox']

package_data = \
{'': ['*']}

install_requires = \
['pyfuse3>=3.0.0,<4.0.0', 'trio>=0.15.1,<0.16.0']

entry_points = \
{'console_scripts': ['fusebox = fusebox.fusebox:main']}

setup_kwargs = {
    'name': 'fusebox',
    'version': '0.1.0',
    'description': 'FUSE-powered sandbox for Gentoo Linux',
    'long_description': None,
    'author': 'Kaoru Esashika',
    'author_email': 'pluser@pluser.net',
    'maintainer': None,
    'maintainer_email': None,
    'url': None,
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'entry_points': entry_points,
    'python_requires': '>=3.6,<4.0',
}


setup(**setup_kwargs)
