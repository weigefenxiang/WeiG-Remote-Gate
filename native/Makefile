CC ?= cc
CFLAGS ?= -O2
CPPFLAGS ?=
LDFLAGS ?=

WARNINGS := -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wconversion -Wstrict-prototypes
TARGET := remote-gate-mapper

.PHONY: all clean check

all: $(TARGET)

$(TARGET): remote-gate-mapper.c
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARNINGS) -std=c11 -o $@ $< $(LDFLAGS)

check: $(TARGET)
	./$(TARGET) >/dev/null 2>&1; test $$? -eq 2

clean:
	rm -f $(TARGET)
