LIBDIR = $(bindir)/ext/aiovelib/aiovelib

FILES = \
	dbus-acsystem.py

LIBS = \
	ext/aiovelib/aiovelib/client.py \
	ext/aiovelib/aiovelib/localsettings.py \
	ext/aiovelib/aiovelib/service.py

help:
	@echo "The following make targets are available"
	@echo " help - print this message"
	@echo " install - install everything"
	@echo " clean - remove temporary files"

clean: ;

install: $(LIBS) $(FILES)
	install -m 755 -d $(DESTDIR)$(bindir)
	cp --parents $^ $(DESTDIR)$(bindir)
	chmod +x $(DESTDIR)$(bindir)/$(firstword $(FILES))

testinstall:
	$(eval TMP := $(shell mktemp -d))
	$(MAKE) DESTDIR=$(TMP) install
	(cd $(TMP) && ./dbus-acsystem.py --help > /dev/null)
	-rm -rf $(TMP)

.PHONY: help install_app install_lib clean
