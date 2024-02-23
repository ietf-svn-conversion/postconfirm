#!/usr/local/python2.7/bin/python2
# -*- python -*-

"""
NAME
	%(program)s - Mail confirmation system (daemon part)

SYNOPSIS
	%(program)s [OPTIONS]

DESCRIPTION
        %(program)s is the long-running (daemon) part of a client-server
        program which handles email confirmations. It is intended as a
        front-end to mailing lists. It provides funcitonality which is a
        subset of TMDA, but is adapted to high-volume usage and does not have
        anywhere near all the bells and whistles which TMDA has. On the other
        hand, since the whitelist lookup is done by the long-running server
        part, the overhead of doing a verification that a poster has a
        confirmed address is much smaller than for TMDA.

        Early tests indicate that with a whitelist of 16000 entries a lookup
        costs about 0.01 seconds and about ~5 Mbytes for the server daemon, in
        contrast whith TMDA which cost between ~10s and ~600s and ~98 Mb *per
        lookup* as it was set up in front of the IETF lists.

        Somewhat simplified, the flow for regular mail is as follows:

           mail agent
               |
               v
           postconfirm/mailman wrapper [copy] -> cached in cache directory
               |
               v
           postconfirmc <==> postconfirmd
               |
               v
           postconfirm/mailman wrapper [white] -> Mailman
             [grey]
               |
               v
           (waiting for confirmation)

        In the start of the flow above, a message comes in. If the envelope
        From is in the lists known by postconfirmd, it is passed through the
        mailman/ postconfirm wrapper, where postconfirmc is called to talk
        with postconfirmd and get either an OK to pass the message to Mailman,
        or cache it.
        
        In more detail, this is the sequence of actions that postconfirm goes
        through when processing an incoming email message:

        1. The mail is put in the cache directory.

        2. If the message is a delivery-status report (content-type
           multipart/report, report-type delivery-status) then this is logged,
           and no further action is taken.

        3. If the precedence matches the bulk_regex setting in the
           configuration file, then:
           
           a. if the envelope sender is in the whitelist or the white_regex
               list, then the message is forwarded directly.

           b. if not, the receipt of a bulk message is logged, and no further
               action is taken.

        4. If the message has an auto-submitted header, and the value matches
           the auto_submitted_regex in the configuration file, then:
           
           a. if the envelope sender is in the whitelist or the white_regex
              list, then the message is forwarded directly.

           b. if not, the receipt of a bulk message is logged, and no further
              action is taken.

        5. If the subject matches the regex for postconfirm's confirmation
           email subject, the confirmation is processed, and then:
           
           a. if the confirmation is valid, the held message is forwarded,
              and the confirmed address is added to the whitelist.

           b. if not, the failed confirmation is logged, and the message
              is saved.

        6. If the envelope sender is in the whitelist or the white_regex list,
           the message is forwarded.

        7. If there was no match earlier, a confirmation request is sent out
           for the message.


%(options)s

FILES
        %(program)s reads its configuration from the following files (if found),
        in the given order:
        
            <bin-dir>/postconfirm.conf
            /etc/postconfirm.conf
            /etc/postconfirm/postconfirm.conf
            ~/.postconfirmrc

        where <bin-dir> is the directory where postconfirmd is installed.

AUTHOR
	Written by Henrik Levkowetz, <henrik@merlot.tools.ietf.org>. Uses the
        daemonize module from Chad J. Schroeder, from the Python Cookbook at
        http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/278731, and
        the readyexec module from Frank J. Tobin, available at
        http://readyexec.sourceforge.net/.

COPYRIGHT
	Copyright 2008 Henrik Levkowetz

	This program is free software; you can redistribute it and/or modify
	it under the terms of the GNU General Public License as published by
	the Free Software Foundation; either version 2 of the License, or (at
	your option) any later version. There is NO WARRANTY; not even the
	implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
	PURPOSE. See the GNU General Public License for more details.

"""

import re
import sys
import os.path
import stat
import getopt
import config
import StringIO
import syslog
from __init__ import __version__

# ------------------------------------------------------------------------------
# Misc. metadata


program = os.path.basename(sys.argv[0])
progdir = os.path.dirname(sys.argv[0])

# ------------------------------------------------------------------------------
# Set up logging

syslog.openlog("postconfirmd", syslog.LOG_PID)
log = syslog.syslog

log("Postconfirm daemon v%s starting (%s)." % (__version__, __file__))

# ------------------------------------------------------------------------------
# Read config file


merger = config.ConfigMerger(lambda x, y, z: "overwrite")

default = """
foreground:         False
debug:              False
socket_path:        "/var/run/postconfirm/socket"
archive_url_pattern: "http://mailarchive.ietf.org/arch/msg/%(list)s/%(hash)s"
auto_submitted_regex:	"^auto-"
mailman_dir:        "/usr/lib/mailman"
remember_bounce_hours: 12
confirm:
{
    smtp:
    {
        host: localhost
        port: 25
    }
}
dmarc:
{
    domain:         "dmarc.ietf.org"
    resolver:
    {
        # seconds
        timeout: 3                      
        lifetime: 5
    }
    rewrite:
    {
        quote_char: "="
        smtp:
        {
            host: localhost
            port: 10028
        }
    }
    reverse:
    {
        smtp:
        {
            host: localhost
            port: 10025
        }
    }
}
"""

default = StringIO.StringIO(default)
conf = config.Config(default)

for conffile in [progdir+"/postconfirm.conf",
                "/etc/postconfirm.conf",
                "/etc/postconfirm/postconfirm.conf",
                os.path.expanduser("~/.postconfirmrc"),
            ]:
    if os.path.exists(conffile):
        log("Reading configuration from %s" % conffile)
        merger.merge(conf, config.Config(conffile))
try:
    conf.dmarc.rewrite.quote_char
except AttributeError:
    conf.dmarc.rewrite.quote_char = '='

# import pprint
# pprint.pprint(dict(conf), sys.stdout, 4, 40)

# ------------------------------------------------------------------------------
# Create list of options, for the help text

options = ""
for line in re.findall("\n +(if|elif) +opt in \[(.+)\]:\s+#(.+)\n", open(__file__.replace(".pyc", ".py")).read()):
    if not options:
        options += "OPTIONS\n"
    options += "        %-16s %s\n" % (line[1].replace('"', ''), line[2])
options = options.strip()

# ------------------------------------------------------------------------------
# Process options

# with ' < 1:' on the next line, this is a no-op:
if len(sys.argv) < 1:
    print __doc__ % locals()
    sys.exit(1)

try:
    opts, args = getopt.gnu_getopt(sys.argv[1:], "dfhs:V", ["debug", "foreground", "help", "socket=", "version", ])
except Exception, e:
    print "%s: %s" % (program, e)
    sys.exit(1)

# process option switches
for opt, value in opts:
    if not opt:
        pass
    elif opt in ["-d", "--debug"]:      # Run with debug output
        conf.debug = True
    elif opt in ["-f", "--foreground"]: # Run in the foreground, don't daemonize
        conf.foreground = True
    elif   opt in ["-h", "--help"]:     # Output this help, then exit
        print __doc__ % globals()
        sys.exit(1)
    elif opt in ["-s", "--socket"]:     # Specify the socket path
        conf.socket_path = value
    elif opt in ["-V", "--version"]:    # Output version, then exit
        print program, __version__
        sys.exit(0)


# ------------------------------------------------------------------------------

import daemonize
import grp
import pwd
import service
import sockserver
import syslog

# ------------------------------------------------------------------------------
# Utility functions

def mkdir(path):
    if not os.path.exists(path):
        print "Creating directory '%s'" % path
        os.mkdir(path)
        return True
    return False

def mkfile(file):
    path = os.path.dirname(file)
    mkdir(path)
    if not os.path.exists(file):
        os.mknod(file)
        return True
    return False

# ------------------------------------------------------------------------------
# Some assertions
assert os.path.exists(conf.mail_template), "Could not find mail template at configured path: %s" % conf.mail_template
assert type(conf.whitelists) == config.Sequence, "The whitelist configuration should be a list of file paths."

# ------------------------------------------------------------------------------
# Create directories and do initialization, as needed:

def run():
    sys.stderr.write("\nPostconfirm daemon v%s starting (%s).\n" % (__version__, __file__))

    mkdir(conf.mail_cache_dir)

    if mkfile(conf.key_file):
        keyfile = open(conf.key_file, "w")
        keyfile.write(os.urandom(128))
        keyfile.close()

    mkfile(conf.confirmlist)
    #mkfile(conf.bouncelist)

    mkdir(os.path.dirname(conf.socket_path))



    # ------------------------------------------------------------------------------
    # Maybe daemonize

    # Get user and group we should execute as
    user, pw, uid, gid, gecos, home, shell = list(pwd.getpwnam(conf.daemon_user))
    if "daemon_group" in conf:
        group, gpw, gid, members = list(grp.getgrnam(conf.daemon_group))

    if not conf.foreground:
        pidfname = "/var/run/%s.pid" % program

        pidfile = open(pidfname, "w")
        os.chown(pidfile.name, uid, gid)
        pidfile.close()

        os.setgid(gid)
        os.setuid(uid)
        daemonize.createDaemon()

        pidfile = open(pidfname, "w")
        pidfile.write("%s" % os.getpid())
        pidfile.close()
    else:
        log("Not daemonizing.")
        sys.stderr.write("Not daemonizing.\n")

    sys.stderr.write("Will listen on unix domain socket '%s'\n" % conf.socket_path)

    # ------------------------------------------------------------------------------
    # connect stdout and stderr to syslog, to catch messages, exceptions, traceback
    if not conf.foreground:
        log("Redirecting stdout and stderr to syslog")
        syslog.write = syslog.syslog
        sys.stdout = syslog
        sys.stderr = syslog

    # ------------------------------------------------------------------------------
    # Set up the service
    service.setup(conf, args)

    # ------------------------------------------------------------------------------
    # Start the server

    try:
        server = sockserver.ReadyExec(service.handler, conf.socket_path, debug=conf.debug)
    except IOError as e:
        log(" ** Tried to set up server to read from socket %s, but got an exception: '%s'" % (conf.socket_path, e))
        raise

    os.chmod(conf.socket_path, stat.S_IRWXU | stat.S_IRWXG )
    os.chown(conf.socket_path, uid, gid)

    try:        
        server.serve_forever()
    finally:
        server.server_close()

if __name__ == '__main__':
    run()
    
