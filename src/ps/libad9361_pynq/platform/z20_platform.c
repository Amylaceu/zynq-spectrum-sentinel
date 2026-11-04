/* Linux userspace backend for the verified Z20 bring-up address map. */
#include "z20_platform.h"
#include "no_os_axi_io.h"
#include "no_os_delay.h"
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

static int memfd = -1, lockfd = -1;
static volatile uint32_t *spi, *gpio, *adc;
static uint32_t rd(volatile uint32_t *p, unsigned off) {
    __sync_synchronize();
    uint32_t value = p[off / 4];
    __sync_synchronize();
    return value;
}
static void wr(volatile uint32_t *p, unsigned off, uint32_t value) {
    __sync_synchronize(); p[off / 4] = value; __sync_synchronize();
}
static double monotonic_s(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}
void no_os_udelay(uint32_t us) {
    struct timespec t = { us / 1000000, (us % 1000000) * 1000 };
    while (nanosleep(&t, &t) && errno == EINTR) {}
}
void no_os_mdelay(uint32_t ms) {
    while (ms >= 1000) { no_os_udelay(1000000); ms -= 1000; }
    no_os_udelay(ms * 1000);
}
struct no_os_time no_os_get_time(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return (struct no_os_time){ t.tv_sec, t.tv_nsec / 1000 };
}
void z20_platform_hold_reset(void) { if (gpio) wr(gpio, 0, 0); }
void z20_platform_close(void) {
    z20_platform_hold_reset();
    if (spi) { wr(spi, 0x60, 0x196); wr(spi, 0x70, 0xffffffff); munmap((void *)spi, 4096); }
    if (gpio) munmap((void *)gpio, 4096);
    if (adc) munmap((void *)adc, 65536);
    spi = gpio = adc = NULL;
    if (memfd >= 0) close(memfd);
    memfd = -1;
    if (lockfd >= 0) { flock(lockfd, LOCK_UN); close(lockfd); }
    lockfd = -1;
}
int z20_platform_open(void) {
    if (memfd >= 0) return -EBUSY;
    lockfd = open("/run/lock/zss_ad9361.lock", O_CREAT | O_RDWR, 0600);
    if (lockfd < 0) return -errno;
    if (flock(lockfd, LOCK_EX | LOCK_NB)) { int e = -errno; close(lockfd); lockfd = -1; return e; }
    memfd = open("/dev/mem", O_RDWR | O_SYNC);
    if (memfd < 0) { int e = -errno; z20_platform_close(); return e; }
    void *p = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, memfd, 0x41e00000);
    if (p == MAP_FAILED) goto fail;
    spi = p;
    p = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, memfd, 0x41200000);
    if (p == MAP_FAILED) goto fail;
    gpio = p;
    p = mmap(NULL, 65536, PROT_READ | PROT_WRITE, MAP_SHARED, memfd, 0x79020000);
    if (p == MAP_FAILED) goto fail;
    adc = p;
    wr(gpio, 0, 0); /* RF reset asserted, ENABLE/TXNRX=0. */
    return 0;
fail: {
    int e = -errno; z20_platform_close(); return e;
}}
int32_t no_os_axi_io_read(uint32_t base, uint32_t offset, uint32_t *value) {
    uint64_t a = (uint64_t)base + offset;
    if (!adc || !value || (a & 3) || a < 0x79020000 || a >= 0x79030000) return -EINVAL;
    *value = rd(adc, a - 0x79020000); return 0;
}
int32_t no_os_axi_io_write(uint32_t base, uint32_t offset, uint32_t value) {
    uint64_t a = (uint64_t)base + offset;
    if (!adc || (a & 3) || a < 0x79020000 || a >= 0x79030000) return -EINVAL;
    wr(adc, a - 0x79020000, value); return 0;
}
static int32_t spi_init(struct no_os_spi_desc **out, const struct no_os_spi_init_param *p) {
    if (!spi || p->chip_select != 0 || p->mode != NO_OS_SPI_MODE_1 || p->bit_order) return -EINVAL;
    *out = calloc(1, sizeof(**out));
    if (!*out) return -ENOMEM;
    (*out)->mode = p->mode;
    wr(spi, 0x40, 0x0a); wr(spi, 0x70, 0xffffffff);
    wr(spi, 0x60, 0x1f6); wr(spi, 0x60, 0x196);
    return 0;
}
static int32_t spi_remove(struct no_os_spi_desc *p) { free(p); return 0; }
static int32_t spi_transfer(struct no_os_spi_desc *desc, uint8_t *data, uint16_t n) {
    (void)desc;
    int ret = 0;
    if (!spi || !data || !n) return -EINVAL;
    wr(spi, 0x60, 0x1f6); wr(spi, 0x60, 0x196); wr(spi, 0x70, 0xfffffffe);
    for (unsigned start = 0; start < n; start += 16) {
        unsigned count = n - start > 16 ? 16 : n - start;
        for (unsigned i = 0; i < count; ++i) wr(spi, 0x68, data[start + i]);
        wr(spi, 0x60, 0x96);
        double deadline = monotonic_s() + 0.25;
        for (unsigned i = 0; i < count; ++i) {
            uint32_t status;
            while ((status = rd(spi, 0x64)) & 1) {
                if (status & 0x10) { ret = -EIO; goto done; }
                if (monotonic_s() >= deadline) { ret = -ETIMEDOUT; goto done; }
                no_os_udelay(5);
            }
            if (status & 0x10) { ret = -EIO; goto done; }
            data[start + i] = rd(spi, 0x6c) & 0xff;
        }
        wr(spi, 0x60, 0x196);
    }
done:
    wr(spi, 0x60, 0x196); wr(spi, 0x70, 0xffffffff);
    if (ret) z20_platform_hold_reset();
    return ret;
}
const struct no_os_spi_platform_ops z20_spi_ops = {
    .init = spi_init, .remove = spi_remove, .write_and_read = spi_transfer
};
static int32_t gpio_get(struct no_os_gpio_desc **out, const struct no_os_gpio_init_param *p) {
    if (!gpio || p->number < 0 || p->number > 6) return -EINVAL;
    *out = calloc(1, sizeof(**out));
    if (!*out) return -ENOMEM;
    (*out)->number = p->number;
    return 0;
}
static int32_t gpio_remove(struct no_os_gpio_desc *p) { free(p); return 0; }
static int32_t gpio_set(struct no_os_gpio_desc *p, uint8_t v) {
    if (!gpio || !p || v > 1) return -EINVAL;
    uint32_t mask = 1u << p->number;
    wr(gpio, 0, (rd(gpio, 0) & ~mask) | (v ? mask : 0)); return 0;
}
static int32_t gpio_input(struct no_os_gpio_desc *p) { (void)p; return -ENOTSUP; }
static int32_t gpio_dir(struct no_os_gpio_desc *p, uint8_t *v) { (void)p; *v = NO_OS_GPIO_OUT; return 0; }
static int32_t gpio_value(struct no_os_gpio_desc *p, uint8_t *v) { *v = (rd(gpio, 0) >> p->number) & 1; return 0; }
const struct no_os_gpio_platform_ops z20_gpio_ops = {
    .gpio_ops_get = gpio_get, .gpio_ops_get_optional = gpio_get,
    .gpio_ops_remove = gpio_remove, .gpio_ops_direction_input = gpio_input,
    .gpio_ops_direction_output = gpio_set, .gpio_ops_set_value = gpio_set,
    .gpio_ops_get_direction = gpio_dir, .gpio_ops_get_value = gpio_value
};
