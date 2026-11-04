/* F3 opt-in OTA adapter. Frozen RX adapter/third-party code stay unchanged.
 * TX2 remains maximally attenuated. No raw SPI write API is exported here.
 * A process-local heartbeat watchdog asserts RF reset after two seconds.
 * It does not survive SIGKILL/kernel failure; do not call it a hardware interlock.
 */
#include <pthread.h>
#include <time.h>
void f3_receive_close(void);
#define z20_ad9361_close f3_receive_close
#define z20_set_tx_attenuation f3_receive_attenuation
#include "ad9361_api_c.c"
#undef z20_ad9361_close
#undef z20_set_tx_attenuation

static pthread_t guard_thread;
static pthread_mutex_t guard_lock = PTHREAD_MUTEX_INITIALIZER;
static int guard_created, guard_running, guard_tripped, prepared;
static double heartbeat_deadline;

static int fail_reset(int ret) {
    if (ret) {
        pthread_mutex_lock(&guard_lock);
        guard_tripped = 1;
        z20_platform_hold_reset();
        pthread_mutex_unlock(&guard_lock);
    }
    return ret;
}

static double seconds_now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}

static void *watchdog(void *unused) {
    (void)unused;
    for (;;) {
        no_os_mdelay(25);
        pthread_mutex_lock(&guard_lock);
        if (!guard_running) { pthread_mutex_unlock(&guard_lock); return NULL; }
        if (seconds_now() > heartbeat_deadline) {
            guard_tripped = 1;
            guard_running = 0;
            z20_platform_hold_reset();
            pthread_mutex_unlock(&guard_lock);
            return NULL;
        }
        pthread_mutex_unlock(&guard_lock);
    }
}

static void stop_watchdog(void) {
    pthread_mutex_lock(&guard_lock);
    guard_running = 0;
    pthread_mutex_unlock(&guard_lock);
    if (guard_created) { pthread_join(guard_thread, NULL); guard_created = 0; }
}

int z20_f3_watchdog_status(void) {
    pthread_mutex_lock(&guard_lock);
    int status = guard_tripped ? -ETIMEDOUT : 0;
    pthread_mutex_unlock(&guard_lock);
    return status;
}

int z20_f3_heartbeat(void) {
    int32_t rssi = 0;
    int sample_ret = z20_get_rx_rssi(RX1, &rssi);
    if (sample_ret || rssi > -30000) {
        return fail_reset(sample_ret ? sample_ret : -ERANGE);
    }
    pthread_mutex_lock(&guard_lock);
    int ret = guard_tripped ? -ETIMEDOUT : (!guard_running ? -EPERM : 0);
    if (!ret) heartbeat_deadline = seconds_now() + 2.0;
    pthread_mutex_unlock(&guard_lock);
    return ret;
}

/* Strengthen the inherited setter: F3 can NEVER request less than 40dB. */
int z20_set_tx_attenuation(uint32_t mdb) {
    if (!phy || mdb < 40000 || mdb > 89750 || mdb % 250) return -EINVAL;
    if (z20_f3_watchdog_status()) return -ETIMEDOUT;
    uint32_t before = 0, a = 0, b = 0;
    int ret = ad9361_get_tx_attenuation(phy, TX1, &before);
    if (ret) return fail_reset(ret);
    if (mdb < 89750) {
        if (!guard_created || !guard_running || !prepared) return -EPERM;
        if (mdb < before && before-mdb > 3000) return -ERANGE;
        int32_t rssi = 0;
        ret = z20_get_rx_rssi(RX1, &rssi);
        if (ret || rssi > -30000) return fail_reset(ret ? ret : -ERANGE);
        if (mdb < before && rssi+(int32_t)(before-mdb) > -35000)
            return fail_reset(-ERANGE);
    }
    ret = ad9361_set_tx_attenuation(phy, TX1, mdb);
    if (!ret) ret = ad9361_set_tx_attenuation(phy, TX2, 89750);
    if (!ret) ret = ad9361_get_tx_attenuation(phy, TX1, &a);
    if (!ret) ret = ad9361_get_tx_attenuation(phy, TX2, &b);
    if (!ret && (a != mdb || b != 89750)) ret = -EIO;
    return fail_reset(ret);
}

int z20_f3_stop(void) {
    prepared = 0;
    if (!phy) { stop_watchdog(); return -ENODEV; }
    if (guard_tripped) { z20_platform_hold_reset(); stop_watchdog(); return -ETIMEDOUT; }
    int first = ad9361_set_tx_attenuation(phy, TX1, 89750);
    int ret = ad9361_set_tx_attenuation(phy, TX2, 89750);
    if (!first) first = ret;
    ret = ad9361_set_en_state_machine_mode(phy, ENSM_MODE_ALERT);
    if (!first) first = ret;
    if (first) z20_platform_hold_reset();
    stop_watchdog();
    return first;
}

void z20_ad9361_close(void) {
    if (phy) z20_f3_stop();
    stop_watchdog();
    prepared = 0;
    f3_receive_close();
}

int z20_f3_prepare(uint64_t lo_hz) {
    if (!phy || lo_hz != 2450000000ULL || guard_created) return -EINVAL;
    int ret = z20_f3_stop();
    if (ret) return ret;
    phy->pdata->fdd = true;
    ret = ad9361_bist_loopback(phy, 0);
    if (!ret) ret = ad9361_bist_prbs(phy, BIST_DISABLE);
    if (!ret) ret = ad9361_bist_tone(phy, BIST_DISABLE, 0, 0, 0);
    if (!ret) ret = ad9361_set_tx_sampling_freq(phy, 3840000);
    if (!ret) ret = ad9361_set_rx_sampling_freq(phy, 3840000);
    if (!ret) ret = ad9361_set_tx_lo_freq(phy, lo_hz);
    if (!ret) ret = ad9361_set_rx_lo_freq(phy, lo_hz);
    if (!ret) ret = ad9361_set_tx_rf_bandwidth(phy, 1500000);
    if (!ret) ret = ad9361_set_rx_rf_bandwidth(phy, 1500000);
    if (!ret) ret = ad9361_set_en_state_machine_mode(phy, ENSM_MODE_ALERT);
    uint32_t rxrate=0, txrate=0;
    uint64_t rxlo=0, txlo=0;
    if (!ret) ret = ad9361_get_rx_sampling_freq(phy, &rxrate);
    if (!ret) ret = ad9361_get_tx_sampling_freq(phy, &txrate);
    if (!ret) ret = ad9361_get_rx_lo_freq(phy, &rxlo);
    if (!ret) ret = ad9361_get_tx_lo_freq(phy, &txlo);
    if (!ret && (rxrate!=3840000 || txrate!=3840000 || rxlo!=lo_hz || txlo!=lo_hz)) ret=-EIO;
    if (!ret) ret = z20_set_tx_attenuation(89750);
    if (ret) z20_platform_hold_reset();
    else prepared=1;
    return ret;
}

int z20_f3_start(void) {
    if (!phy || !prepared || guard_created || guard_tripped) return -EPERM;
    uint32_t a=0,b=0;
    int ret=ad9361_get_tx_attenuation(phy,TX1,&a);
    if (!ret) ret=ad9361_get_tx_attenuation(phy,TX2,&b);
    if (ret || a!=89750 || b!=89750) return ret ? ret : -EPERM;
    /* Start the watchdog before FDD; never restore cached unmute attenuation. */
    pthread_mutex_lock(&guard_lock);
    heartbeat_deadline=seconds_now()+2.0; guard_running=1;
    pthread_mutex_unlock(&guard_lock);
    ret=pthread_create(&guard_thread,NULL,watchdog,NULL);
    if (ret) {
        pthread_mutex_lock(&guard_lock); guard_running=0;
        pthread_mutex_unlock(&guard_lock); return fail_reset(-ret);
    }
    guard_created=1;
    ret=ad9361_set_en_state_machine_mode(phy,ENSM_MODE_FDD);
    if (ret) { z20_f3_stop(); z20_platform_hold_reset(); }
    return ret;
}

int z20_f3_set_gain(int32_t db) {
    if (!phy || db < 0 || db > 60) return -EINVAL;
    int ret=ad9361_set_rx_gain_control_mode(phy,RX1,RF_GAIN_MGC);
    if (!ret) ret=ad9361_set_rx_rf_gain(phy,RX1,db);
    return ret;
}

int z20_f3_get_tx_lo(uint64_t *hz) {
    return phy && hz ? ad9361_get_tx_lo_freq(phy,hz) : -EINVAL;
}
