CC = clang
CFLAGS = -dynamiclib -fPIC -O2 -Wall
TARGET = interpose.dylib

all: $(TARGET)

$(TARGET): interpose.c
	$(CC) $(CFLAGS) -o $(TARGET) interpose.c

clean:
	rm -f $(TARGET)
