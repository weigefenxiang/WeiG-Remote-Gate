CC ?= cc
CFLAGS ?= -O2
CPPFLAGS ?=
LDFLAGS ?=

VERSION := $(strip $(shell cat ../VERSION 2>/dev/null))
WARNINGS := -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wconversion -Wstrict-prototypes
TARGET := remote-gate-mapper
ENTRY := remote-gate-mapper-entry.c
CORE := remote-gate-mapper.c

.PHONY: all clean check

all: $(TARGET)

$(TARGET): $(ENTRY) $(CORE) ../VERSION
	$(CC) $(CPPFLAGS) -DREMOTE_GATE_VERSION=\"$(VERSION)\" $(CFLAGS) $(WARNINGS) -std=c11 -o $@ $(ENTRY) $(LDFLAGS)

check: $(TARGET)
	./$(TARGET) >/dev/null 2>&1; test $$? -eq 2
	test "$$(./$(TARGET) --version)" = "remote-gate-mapper $(VERSION) api=1"

clean:
	rm -f $(TARGET)
