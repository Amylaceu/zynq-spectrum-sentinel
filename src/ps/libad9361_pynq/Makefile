NOOS ?= ../../third_party/no-OS
CC ?= gcc
CFLAGS += -O2 -fPIC -Wall -Wextra -D_GNU_SOURCE \
 -I$(NOOS)/include -I$(NOOS)/drivers/rf-transceiver/ad9361 \
 -I$(NOOS)/drivers/axi_core/axi_adc_core -I$(NOOS)/drivers/axi_core/axi_dac_core \
 -Iplatform -Iapp
RF := $(NOOS)/drivers/rf-transceiver/ad9361
SRCS := $(RF)/ad9361.c $(RF)/ad9361_api.c $(RF)/ad9361_util.c \
 $(RF)/ad9361_conv.c $(RF)/ad9361_ext_band_ctrl.c \
 $(NOOS)/drivers/axi_core/axi_adc_core/axi_adc_core.c \
 $(NOOS)/drivers/axi_core/axi_dac_core/axi_dac_core.c \
 $(NOOS)/drivers/api/no_os_spi.c $(NOOS)/drivers/api/no_os_gpio.c \
 $(NOOS)/util/no_os_alloc.c $(NOOS)/util/no_os_util.c $(NOOS)/util/no_os_mutex.c \
 platform/z20_platform.c app/z20_init_param.c app/ad9361_api_c.c

libad9361_pynq.so: $(SRCS) platform/z20_platform.h app/app_config.h
	$(CC) $(CFLAGS) -shared -Wl,-z,defs -o $@ $(SRCS) -lm
