# service.py

""" The handler which constitute the actual service.

    Provides whitelist lookups, and generation and verification of
    confirmation requests.  Incoming emails are read on stdin, emails from
    whitelisted or confirmed senders are written to stdout.  Emails are cached
    in a cache directory which is expected to be cleaned out regularly by a
    cronjob.

"""

import os
import re
import sys
import time
import tempfile
import syslog
import base64
import hashlib
import struct
import interpolate
import email
import datetime
import hmac
import signal
import smtplib
from email.MIMEText import MIMEText

log = syslog.syslog

confirm_fmt = "Confirm: %s:%s:%s"
confirm_pat = "Confirm:[ \t\n\r]+.*:.*:.*"

# ------------------------------------------------------------------------------
def filetext(file):
    if os.path.exists(file):
        file = open(file)
        text = file.read()
        file.close
        return text
    else:
        return ""
        
# ------------------------------------------------------------------------------
# Setup: read initial data before daemonizing.

conf = {}
pid  = None
whitelist = set([])
blacklist = set([])
whiteregex = None
hashkey  = None

# ------------------------------------------------------------------------------
def read_whitelist(files):
    global whitelist

    whitelist = set([])
    for file in files:
        if os.path.exists(file):
            file = open(file)
            entries = set(file.read().lower().split())
            whitelist |= entries
            file.close()
            log("Read %s whitelist entries from %s\n" % (len(entries), file.name))
    log("Whitelist size: %s" % (len(whitelist)))

# ------------------------------------------------------------------------------
def read_regexes(files):
    global whiteregex

    regexlist = []
    for file in files:
        if os.path.exists(file):
            file = open(file)
            entries = file.read().split()
            file.close()
            for entry in entries:
                try:
                    dummy = re.compile(entry)
                except Exception, e:
                    log(syslog.LOG_ERR, "Invalid regex (not added to whitelist): %s" % (entry))
                    log(syslog.LOG_ERR, e)
                else:
                    if not entry in regexlist:
                        regexlist.append(entry)
            log("Read %s regexlist entries from %s\n" % (len(entries), file.name))
    log("Regexlist size: %s" % (len(regexlist)))
    if regexlist:
        whiteregex = "^(%s)$" % "|".join(regexlist)

# ------------------------------------------------------------------------------
def read_blacklist(files):
    global blacklist

    blacklist = set([])
    for file in files:
        if os.path.exists(file):
            file = open(file)
            entries = set(file.read().lower().split())
            blacklist |= entries
            file.close()
            log("Read %s blacklist entries from %s\n" % (len(entries), file.name))
    log("Blacklist size: %s" % (len(blacklist)))

# ------------------------------------------------------------------------------
def read_data():
    t1 = time.time()
    try:
        read_whitelist(list(conf.whitelists) + [ conf.confirmlist ])
    except:
        pass

    try:
        read_regexes(list(conf.whiteregex))
    except:
        pass

    try:
        read_blacklist(list(conf.blacklists))
    except:
        pass
    t2 = time.time()
    log(syslog.LOG_INFO, "Wall time for reading data: %.6f s." % (t2 - t1))    

# ------------------------------------------------------------------------------
def sighup_handler(signum, frame):
    """Re-read our data files"""
    read_data()

# ------------------------------------------------------------------------------
def setup(configuration, files):
    global conf
    global pid
    global hashkey

    conf = configuration

    pid = os.getpid()

    hashkey = filetext(conf.key_file)

    read_data()

    signal.signal(signal.SIGHUP, sighup_handler)


# ------------------------------------------------------------------------------
def sendmail(sender, recipient, subject, text, conf={"smtp_host":"localhost",}, headers={}):

    msg = MIMEText(text)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = recipient
    for key in headers:
        msg[key] = headers[key]
    message = msg.as_string()

    try:
        server = smtplib.SMTP(conf["smtp_host"])
        server.sendmail(sender, recipient, message)
        server.quit()
        #log("Sent mail from '%s' to '%s' about '%s'" % (sender, recipient, subject))
        return True
    except Exception, e:
        log(repr(e))

# ------------------------------------------------------------------------------
def cache_mail():
    seconds = base64.urlsafe_b64encode(struct.pack(">i",int(time.time()))).strip("=")
    outfd, outfn = tempfile.mkstemp(seconds, "", conf.mail_cache_dir)
    out = os.fdopen(outfd, "w+")
    for line in sys.stdin:
        out.write(line)
    out.close()
    return outfn

# ------------------------------------------------------------------------------
def hash(bytes):
    return base64.urlsafe_b64encode(hmac.new(hashkey, bytes, hashlib.sha224).digest()).strip("=")

# ------------------------------------------------------------------------------
def make_hash(sender, recipient, filename):
    return hash( "%s-%s-%s" % (sender, recipient, filename, ) )

# ------------------------------------------------------------------------------
def pad(bytes):
    "Pad with '=' till the string is a multiple of 4"
    return bytes + "=" * ((4 - len(bytes) % 4 ) % 4)

# ------------------------------------------------------------------------------
def request_confirmation(sender, recipient, cachefn):
    """Generate a confirmation request, and send it to the poster for confirmation.

    The request subject line contains:
        'Confirm: <recipient>-<date>-<cachefn>-<hash>'
        Hash is calculated over:
        '<key><sender>-<recipient>-<cachefn><key>'

        <sender> is cleartext
        <recipient> is cleartext
        <cachefn> is the tempfile.mkstmp basename
        <key> is binary
    """

    filename = cachefn.split("/")[-1]

    if sender.lower() in set([ "", recipient.lower() ]):
        log(syslog.LOG_INFO, "Skipped requesting confirmation from <%s>" % (sender,))
        return 1

    if sender.lower() in blacklist:
        log(syslog.LOG_INFO, "Skipped confirmation from blacklisted <%s>" % (sender,))
        return 1

    hash_output = make_hash(sender, recipient, filename)

    log(syslog.LOG_INFO, "Requesting confirmation: <%s>, '%s', %s" % (sender, filename, hash_output))

    #print "Hash input: %s" % (hash_input, )
    #print "Hash output: %s" % (hash_output, )

    # The ':' is a convenient separator character as it's not permitted in
    # email addresses, and it's not used in our base64 alphabet.  It also
    # conveniently will lets us separate out the Confirm: part at the same
    # time as we split the interesting stuff into parts.
    subject = confirm_fmt % (recipient, filename, hash_output)

    file = open(cachefn)
    msg = email.message_from_file(file)
    file.close()

    template = filetext(conf.mail_template)
    text = str(interpolate.Interpolator(template))

    sendmail(recipient, sender, subject, text, conf)

    return 1
    

# ------------------------------------------------------------------------------
def verify_confirmation(sender, recipient, msg):
    log(syslog.LOG_DEBUG, "Verifying confirmation...")
    
    subject = msg.get("subject", "")
    subject = re.sub("\s", "", subject)
    dummy, recipient, filename, hash = subject.rsplit(":", 3)

    # Require the sender to be somebody
    if sender == "":
        return 1

    # Require a corresponding message in the cache:
    cachefn = os.path.join(conf.mail_cache_dir, filename)
    if not os.path.exists(cachefn):
        log(syslog.LOG_WARNING, "No cached message for confirmation '%s'" % (filename))
        return 1

    # Require that the hash matches
    good_hash = make_hash(sender, recipient, filename)
    if not good_hash == hash:
        log(syslog.LOG_WARNING, "Received hash didn't match -- make_hash(<%s>, '%s', '%s') -> %s != %s" % (sender, recipient, filename, good_hash, hash))
        return 1

    # We have a valid confirmation -- update the whitelist and the
    # confirmation file
    log(syslog.LOG_INFO, "Adding <%s> to whitelist" % (sender, ))
    whitelist.add(sender)
    file = open(conf.confirmlist, "a")
    file.write("%s\n" % sender)
    file.close()

    # Tell root daemon process to re-read the data files
    os.kill(pid, signal.SIGHUP)

    # Output the cached message and delete the cache file
    log(syslog.LOG_INFO, "Forwarding cached message from <%s> to %s" % (sender, recipient, ))
    file = open(cachefn)
    for line in file:
        sys.stdout.write(line)
    file.close()
    os.unlink(cachefn)

    return 0

# ------------------------------------------------------------------------------
def forward_whitelisted_post(sender, recipient):
    log(syslog.LOG_INFO, "Forwarding from whitelisted sender <%s>" % (sender,))
    for line in sys.stdin:
        sys.stdout.write(line)
    return 0

# ------------------------------------------------------------------------------
def handle_unconfirmed_post(sender, recipient):
    log(syslog.LOG_DEBUG, "Processing mail from <%s> to %s" % (sender, recipient))
    cachefn = cache_mail()

    file = open(cachefn)
    # Limit how much we read -- a confirmation mail shouldn't be larger than
    # a couple of k at the most:
    text = file.read(8192)
    msg = email.message_from_string(text)
    file.close()

    if re.search(confirm_pat, msg.get("subject", "")):
        return verify_confirmation(sender, recipient, msg)
    else:
        return request_confirmation(sender, recipient, cachefn)

# ------------------------------------------------------------------------------
# Service handler

def handler():
    """ Lookup email sender in whitelist; forward or cache email pending confirmation.

        It is expected that the following environment variables set:
        SENDER   : Envelope MAIL FROM address
	RECIPIENT: Envelope RCPT TO address
	EXTENSION: The recipient address extension (after the extension
                   separator character in local_part, usually '+' or '-')

        If we know the extension character (and we do, since we only use
        extensions for confirmation mail, and we generate the confirmation
        address extension using the configured extension character) we could
        easily find the extension ourselves.  However, we go with the above
        for compatibility with TMDA.

        The service handler looks up the sender in the whitelist, and if found,
        the mail on stdin is passed out on stdout.  If not found, the mail is
        instead cached in the configured mail cache directory, and a
        confirmation request is sent to the sender address.  If a reply to the
        confirmation mail is received while the original mail is in the cache,
        the original mail is sent out stdout.  It is expected that a cronjob
        cleans out the cache with desired intervals and cache retention time.
    """

    t1 = time.time()

    for var in ["SENDER", "RECIPIENT" ]:
        if not var in os.environ:
            log(syslog.LOG_ERR, "Environment variable '%s' not set -- can't process input" % (var))
            return 3

    sender  = os.environ["SENDER"].strip()
    recipient=os.environ["RECIPIENT"].strip()

    if   sender.lower() in whitelist or (whiteregex and re.match(whiteregex, sender.lower())):
        err = forward_whitelisted_post(sender, recipient)
    else:
        err = handle_unconfirmed_post(sender, recipient)

    t2 = time.time()
    log(syslog.LOG_INFO, "Wall time in handler: %.6f s." % (t2 - t1))

    if err:
        raise SystemExit(err)

    
