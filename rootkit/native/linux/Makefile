obj-m += hidemod.o

KDIR := /lib/modules/$(shell uname -r)/build
PWD  := $(shell pwd)

all:
	make -C $(KDIR) M=$(PWD) modules

clean:
	make -C $(KDIR) M=$(PWD) clean

install: all
	insmod hidemod.ko

uninstall:
	rmmod hidemod 2>/dev/null || true
