PYTHONPREFIX=/usr/local/python2.7
CFLAGS=-I$(PYTHONPREFIX)/include/python2.7
LDFLAGS=-L$(PYTHONPREFIX)/lib
OFLAGS=-pthread -fno-strict-aliasing -DNDEBUG -g -fwrapv -O2 -fPIC -I/Library/Frameworks/Python.framework/Versions/2.7/include/python2.7
WFLAGS=-Waggregate-return -Wall -Wcast-align -Wcast-qual -Wconversion -Wmissing-declarations -Wmissing-prototypes -Wnested-externs -Wpointer-arith -Wredundant-decls -Wstrict-prototypes -Wwrite-strings
SOFLAGS=$(CFLAGS) -pthread -shared -Wl,-O1 -Wl,-Bsymbolic-functions 

CC=clang
SHELL=/bin/bash

tool := postconfirmd

# The user that the postconfirmd daemon will run as
user := mail

prefix := /usr/local
shared := /usr/share

module := postconfirm

sources = *.py *.c postconfirmd.8 postconfirm.conf confirm.email.template postconfirm.init wrapper INSTALL

binaries = postconfirmc fdpass.so 

# ----------------------------------------------------------------------

include Makefile.common

% : %.c
	$(CC) $(CFLAGS) $(WFLAGS) -o $@ $(LDFLAGS) $<

%.o : %.c
	$(CC) $(CFLAGS) $(OFLAGS) $(WFLAGS) -o $@ -c $<

%.so : %.o
	$(CC) $(SOFLAGS) -o $@ $(LDFLAGS) $<

test: 
	logger -i -t "postconfirm" "test: mark 1"
	sudo -u $(user) postconfirmc --stop || echo postconfirmd not running
	sudo rm -fv /var/run/postconfirm/confirmed # no confirmed addresses
	sleep 1
	sudo -u $(user) postconfirmd
	logger -i -t "postconfirm" "test: mark 3"
	for msg in msg/*; do from=$$(head -n 1 $$msg | awk '{print $$2}'); echo "From: $$from"; cat $$msg | formail -I "List-Id: <testlist.ietf.org>" | sudo -u $(user) SENDER="$$from"  RECIPIENT=testlist@grenache.levkowetz.com postconfirmc; code=$$?; echo "Result: $$code"; [ $$code == 1 ]; done
	cat testfile2.msg | formail -I "List-Id: <testlist.ietf.org>" | sudo -u $(user) SENDER=henrik-two@levkowetz.com RECIPIENT=testlist@grenache.levkowetz.com postconfirmc; code=$$?; echo Result: $$code; [ $$code == 0 ]
	logger -i -t "postconfirm" "test: mark 4"
# 	sleep 3
# 	echo -e "\$$\nR\n~f\n.\n\nx\n" | sudo mail -N
# 	sleep 3
# 	sudo -u $(user) SENDER=henrik@levkowetz.com RECIPIENT=testlist@grenache.levkowetz.com postconfirmc <<< "From: henrik@levkowetz.com\nSubject: Hello $$(date)\n\nHello";	    code=$$?; echo Result: $$code; [ $$code == 0 ]
# 	sudo -u $(user) postconfirmc --stop

install:: postconfirmc postconfirmd postconfirmd.py postconfirm.conf fdpass.so
	logger -i -t "postconfirm" "install: mark 1"
	sudo install -o root    -d /etc/$(module) $(shared)/$(module)/
	sudo install -o $(user) -d /var/run/$(module) /var/cache/$(module)/mail /var/cache/$(module)/pending $prefix/sbin/
	#
	[ -f /etc/$(module)/postconfirm.conf ] || sudo install -o root postconfirm.conf /etc/$(module)/
	[ -f /etc/$(module)/confirm.email.template ] || sudo install -o root confirm.email.template /etc/$(module)/
	#
	if [ ! -f /etc/$(module)/hash.key ]; then head -c 128 /dev/urandom > hash.key; sudo install -o $(user) -m 600 hash.key /etc/$(module)/; rm hash.key; fi
	#
	sudo install -o root -T postconfirm.init /etc/init.d/postconfirmd
	sudo update-rc.d postconfirmd defaults 30 70
	sudo install -o root postconfirmc $(prefix)/bin/
	sudo install -o root *.py *.so wrapper $(shared)/$(module)/
	sudo python -c "import compileall; compileall.compile_dir('$(shared)/$(module)/');"
	sudo ln -sf $(shared)/$(module)/$(tool).py $(prefix)/sbin/$(tool)
	sudo ln -sf $(shared)/$(module)/wrapper $(shared)/$(module)/mailman
	logger -i -t "postconfirm" "install: mark 2"
	sudo /etc/init.d/postconfirmd stop
	logger -i -t "postconfirm" "install: mark 3"
	sleep 1
	logger -i -t "postconfirm" "install: mark 4"
	sudo /etc/init.d/postconfirmd start
	logger -i -t "postconfirm" "install: mark 5"

upload::
	scp -P 25377 $(tool)-$(version).tgz core3.amsl.com://usr/local/share/
