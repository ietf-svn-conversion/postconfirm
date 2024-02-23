
Caution
-------

This is an alpha release.  While the functionality is sound, the
packaging is probably not even beta quality.  Compilation of the
components written in C has only been tested under Linux.

debian-adapted Branch
---------------------

This is the debian-adapted branch.  It contains patches to .c
files to quiet the C compiler and adjust the Python bang-path for
a locally built Python 2 on a host running a recent Debian OS.
(Debian no longer provides Python 2 packages.)

Versions tested:
OS: Debian 12.4 Bookworm
C compiler: Debian clang version 14.0.6 (x86_64-pc-linux-gnu, posix threads)
C library: 2.36-9+deb12u3
Python: 2.7.18

Description
-----------

postconfirm consists of postconfirmd, which is the long-running
(daemon) part, and postconfirmc, which is the client part of a
client-server program which handles email confirmations. It is
intended as a front-end to mailing lists. It provides
funcitonality which is a subset of TMDA, but is adapted to
high-volume usage and does not have anywhere near all the bells
and whistles which TMDA has. On the other hand, since the
whitelist lookup is done by the long-running server part, the
overhead of doing a verification that a poster has a confirmed
address is much smaller than for TMDA.  This makes it a factor
1000 or more faster than TMDA in production, with a memory footprint
a factor 20 smaller.


