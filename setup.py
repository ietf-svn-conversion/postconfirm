#!/usr/local/python2.7/bin/python2
# --------------------------------------------------
# Copyright The IETF Trust 2011, All Rights Reserved
# --------------------------------------------------

import re
import os.path
import sys

from setuptools import setup, find_packages, Extension
from setuptools.command.install import install
from distutils.ccompiler import new_compiler
from codecs import open

CONF_FILE_DIR = '/etc/postconfirm/'

def maybe_chown(path, uid, gid):
    try:
        os.chown(path, uid, gid)
    except OSError:
        sys.stderr.write("   WARNING: Failed chown %s:%s %s\n" % (uid, gid, path))
        pass

def maybe_chmod(path, mode):
    try:
        os.chmod(path, mode)
    except OSError:
        sys.stderr.write("   WARNING: Failed chmod %s %s\n" % (mode, path))
        pass

class PostInstallCommand(install):
    """Post-installation for installation mode."""
    def run(self):
        import config, pwd, grp, sys, stat

        # -------------------------
        # Run the base installation
        install.run(self)

        # -------------------------
        # Post-install actions
        # Get config
        merger = config.ConfigMerger(lambda x, y, z: "overwrite")
        conf = config.Config()
        conf_file = os.path.join(CONF_FILE_DIR, 'postconfirm.conf')
        for cf in [
                    "/etc/postconfirm.conf",
                    "/etc/postconfirm/postconfirm.conf",
                    conf_file,
                    os.path.expanduser("~/.postconfirmrc"),
                ]:
            if os.path.exists(cf):
                merger.merge(conf, config.Config(cf))
        # Get user and group we should execute as
        user, pw, uid, gid, gecos, home, shell = list(pwd.getpwnam(conf.daemon_user))
        if "daemon_group" in conf:
            group, gpw, gid, members = list(grp.getgrnam(conf.daemon_group))
        # Set correct file owner, group and mode
        maybe_chown(conf_file, uid, gid)
        if not os.path.exists(conf.key_file):
            with open(conf.key_file, "wb") as k:
                with open('/dev/random') as r:
                    rand = r.read(128)
                    k.write(rand)
        maybe_chown(conf.key_file, uid, gid)
        maybe_chmod(conf.key_file, 0o600)
        postconfirmc = os.path.join(self.install_scripts, 'postconfirmc')
        maybe_chown(postconfirmc, uid, gid)
        maybe_chmod(postconfirmc, stat.S_ISUID|0o755 )

here = os.path.abspath(os.path.dirname(__file__))

# Get the long description from the README file
with open(os.path.join(here, 'README.rst'), encoding='utf-8') as file:
    long_description = file.read()

# Get the requirements from the local requirements.txt file
with open(os.path.join(here, 'requirements.txt'), encoding='utf-8') as file:
    requirements = file.read().splitlines()

# Get the requirements from the local manifest file
with open(os.path.join(here, 'MANIFEST.in'), encoding='utf-8') as file:
    extra_files = [ l.split()[1] for l in file.read().splitlines() if l ]

conf_files = []
for fn in ['postconfirm.conf', 'confirm.email.template']:
    if not os.path.exists(os.path.join(CONF_FILE_DIR, fn)):
        # this will be added to setup(data_files=...) below, so use data_files
        # semantics:
        sys.stderr.write("Adding conf_file %s\n" % os.path.join(CONF_FILE_DIR, fn))
        conf_files.append( (CONF_FILE_DIR, [ fn, ]) )

def parse(changelog):
    ver_line = "^([a-z0-9+-]+) \(([^)]+)\)(.*?) *$"
    sig_line = "^ -- ([^<]+) <([^>]+)>  (.*?) *$"
    #
    entries = []
    if type(changelog) == type(''):
        changelog = open(changelog)
    for line in changelog:
        if re.match(ver_line, line):
            package, version, rest = re.match(ver_line, line).groups()
            entry = {}
            entry["package"] = package
            entry["version"] = version
            entry["logentry"] = ""
        elif re.match(sig_line, line):
            author, email, date = re.match(sig_line, line).groups()
            entry["author"] = author
            entry["email"] = email
            entry["datetime"] = date
            entry["date"] = " ".join(date.split()[:3])
            entries += [ entry ]
        else:
            entry["logentry"] += line
    changelog.close()
    entry["logentry"] = entry["logentry"].strip()
    return entries

changelog_entry_template = """
Version %(version)s (%(date)s)
------------------------------------------------

%(logentry)s"""

long_description += """
Changelog
=========
""" + "\n".join([ changelog_entry_template % entry for entry in parse("changelog")[:3] ])



import postconfirm

compiler = new_compiler()
client_o_files = compiler.compile(['postconfirmc.c',])
compiler.link_executable(client_o_files, 'postconfirmc')

setup(
    name='postconfirm',

    # Versions should comply with PEP440.  For a discussion on single-sourcing
    # the version across setup.py and the project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    version=postconfirm.__version__,

    description='Mailing list posting confirmation daemon',
    long_description=long_description,

    # The project's main homepage.
    #url = ''

    # Author details
    author='Henrik Levkowetz',
    author_email='henrik@levkowetz.com',

    # Choose your license
    license='Simplified BSD',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 3 - Alpha',

        # Indicate who your project is intended for
        'Intended Audience :: Other Audience',
        'Topic :: Communications :: Email',

        # Pick your license as you wish (should match "license" above)
        'License :: OSI Approved :: BSD License',

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        #'Programming Language :: Python :: 3',
        #'Programming Language :: Python :: 3.3',
        #'Programming Language :: Python :: 3.4',
        #'Programming Language :: Python :: 3.5',
    ],

    ext_modules = [
        Extension('fdpass', ['fdpass.c',]),
    ],

    # What does your project relate to?
    keywords='Mailing list posting confirmation daemon',

    # You can just specify the packages manually here if your project is
    # simple. Or you can use find_packages().
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),

    # Alternatively, if you want to distribute just a my_module.py, uncomment
    # this:
    #py_modules=["debug"],

    # Setup requirements
    setup_requires=['config', ],

    # List run-time dependencies here.  These will be installed by pip when
    # your project is installed. For an analysis of "install_requires" vs pip's
    # requirements files see:
    # https://packaging.python.org/en/latest/requirements.html
    install_requires=requirements,

    # List additional groups of dependencies here (e.g. development
    # dependencies). You can install these using the following syntax,
    # for example:
    # $ pip install -e .[dev,test]
    extras_require={
        'dev': ['twine',],
        #'test': ['coverage'],
    },

    # If there are data files included in your packages that need to be
    # installed, specify them here.  If using Python 2.6 or less, then these
    # have to be included in MANIFEST.in as well.
    #package_data={
    #},

    # If set to True, this tells setuptools to automatically include any data
    # files it finds inside your package directories that are specified by your
    # MANIFEST.in file. For more information, see the section below on Including
    # Data Files.
    include_package_data=True,
    
    # Although 'package_data' is the preferred approach, in some case you may
    # need to place data files outside of your packages. See:
    # http://docs.python.org/3.4/distutils/setupscript.html#installing-additional-files # noqa
    data_files=[
        ('/usr/share/man/man1', ['postconfirmc.1',]),
        ('/usr/share/man/man8', ['postconfirmd.8',]),
    ]+conf_files,

    # To provide executable scripts, use entry points in preference to the
    # "scripts" keyword. Entry points provide cross-platform support and allow
    # pip to create the appropriate form of executable for the target platform.
    entry_points={
        'console_scripts': [
            'postconfirmd=postconfirm.postconfirmd:run',
        ],
    },

    scripts = [
        'postconfirmc',
    ],

    # We're reading schema files from a package directory.
    zip_safe = True,

    cmdclass = {
        'install': PostInstallCommand,
    },
)
