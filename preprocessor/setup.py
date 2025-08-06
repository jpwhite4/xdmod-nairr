#!/usr/bin/env python
# -*- encoding: utf-8 -*-

# import re
from glob import glob
from os.path import basename, dirname, join, splitext

from setuptools import find_packages, setup


def read(*names, **kwargs):
    """Read description files."""
    path = join(dirname(__file__), *names)
    with open(path, encoding=kwargs.get('encoding', 'utf8')) as fh:
        return fh.read()


long_description = '{}\n{}'.format(
    read('README.md'),
    read('CHANGELOG.md'),
    )

setup(
    name='xdmod-preprocessor',
    version='1.0.0',
    description='Utility scripts to manipulate resource manager logs for XDMoD ingest',
    long_description=long_description,
    long_description_content_type='text/markdown',
    license='GPLv3',
    author='Joseph P. White',
    author_email='jpwhite4@buffalo.edu',
    url='https://github.com/ubccr/xdmod-nairr',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    py_modules=[splitext(basename(i))[0] for i in glob("src/*.py")],
    include_package_data=True,
    zip_safe=False,
    python_requires='>=3.6, <4',
    install_requires=[
        ],
    extras_require={
        # eg:
        #   'rst': ['docutils>=0.11'],
        #   ':python_version=="2.6"': ['argparse'],
        },
    setup_requires=[
        #   'pytest-runner',
        #   'setuptools_scm>=3.3.1',
        ],
    entry_points={
        'console_scripts': [
            'xdmod-preprocess= preprocessor.cli_script:main',
            ]
        #
        },
    )
