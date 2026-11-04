#pragma once
#include <stdint.h>
#include "no_os_gpio.h"
#include "no_os_spi.h"
extern const struct no_os_spi_platform_ops z20_spi_ops;
extern const struct no_os_gpio_platform_ops z20_gpio_ops;
int z20_platform_open(void);
void z20_platform_close(void);
void z20_platform_hold_reset(void);
