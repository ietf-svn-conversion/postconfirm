#!/usr/local/python2.7/bin/python2
#
# test rig to run messages through postconfirm daemon
#

import service
import sys
import os
import config

# stub configuration that is also a dict
# for conf.confirm.smtp.host etc.
class ConfigMailRewriteSmtp: # conf.confirm.smtp and conf.dmarc.rewrite.smtp
    host = 'localhost'
    port = 10028

class ConfigDmarcRequire: # conf.dmarc.require
    header = dict()

class ConfigMailRewrite: # conf.confirm and conf.dmarc.rewrite
    smtp = ConfigMailRewriteSmtp()
    quote_char = '='    # for DMARC rewrite addr
    require = ConfigDmarcRequire()
    
class ConfigDmarcResolver: # conf.dmarc.resolver
    lifetime = 10
    timeout = 10

class ConfigMail: # conf.dmarc
    rewrite = ConfigMailRewrite()
    domain = 'dmarc.ietf.org'
    resolver= ConfigDmarcResolver()

class Config(dict):
    mail_cache_dir = 'cache'
    key_file = 'hash.key'
    whitelists = ['whitelist']
    confirmlist = 'confirmlist'
    whiteregex = ('whiteregex')
    blacklists = ('blacklist')
    blackregex = ('blackregex')
    archive_url_pattern = "http://mailarchive.ietf.org/arch/msg/%(list)s/%(hash)s"
    bulk_regex = "(junk|list|bulk|auto_reply)"
    auto_submitted_regex = "^auto-"
    mail_template = "confirm.email.template"
    admin_address = "postmaster@test.ietf.org"
    remail_sender = "mailforward@ietf.org"

    # stubbed out in test, make placeholders for intermediate configs
    dmarc = ConfigMail()
    confirm = ConfigMailRewrite()

# test routines to plug into the service
class Testing:
    def send_smtp(self, fromaddr, toaddrs, msg):
        print "=== mail from %s to %s ===" % (fromaddr, toaddrs)
        print msg,
        print "======"

    def getlistinfo(self):
        """
        fake listinfo per mailman
        """
        listinfo = {
            'ietf': { 'archive': True },
            'iesg': { 'archive': False }
            }
        return listinfo
    
conf = Config() # make an instance

# sys.argv = ['test', '-f' ,'johnl@taugh.com' ,'confirm', 'expand-blurch-chairs' ]
os.environ["SENDER"] = 'johnl@taugh.com'

service.testing = Testing() # do testing

service.setup(conf, None)   # dummy files argument

service.handler()
