#include "ad9361.h"
#include "ad9361_api.h"
#include "z20_platform.h"
#include "axi_adc_core.h"
#include "no_os_delay.h"
#include <errno.h>
#include <stdint.h>

extern AD9361_InitParam *z20_init_parameters(void);
static struct ad9361_rf_phy *phy;

/* RX plus muted internal digital diagnostics; no antenna-TX enable API. */
int z20_ad9361_open(void) {
    if (phy) return -EBUSY;
    int ret = z20_platform_open();
    if (ret) return ret;
    ret = ad9361_init(&phy, z20_init_parameters());
    if (ret) { phy = NULL; z20_platform_close(); return ret; }
    ret = ad9361_set_tx_attenuation(phy, TX1, 89750);
    if (!ret) ret = ad9361_set_tx_attenuation(phy, TX2, 89750);
    if (!ret) ret = ad9361_set_en_state_machine_mode(phy, ENSM_MODE_ALERT);
    if (ret) z20_platform_hold_reset();
    return ret;
}
void z20_ad9361_close(void) {
    if (phy) {
        ad9361_tx_mute(phy, 1);
        ad9361_set_tx_attenuation(phy, TX1, 89750);
        ad9361_set_tx_attenuation(phy, TX2, 89750);
        ad9361_set_en_state_machine_mode(phy, ENSM_MODE_ALERT);
        ad9361_bist_loopback(phy, 0);
    }
    z20_platform_hold_reset();
    if (phy) { ad9361_remove(phy); phy = NULL; }
    z20_platform_close();
}
int z20_set_tx_attenuation(uint32_t mdb) {
    if (!phy || mdb>89750 || mdb<30000) return -EINVAL;
    int ret=ad9361_set_tx_attenuation(phy,TX1,mdb);
    if (!ret) ret=ad9361_set_tx_attenuation(phy,TX2,mdb);
    return ret;
}
int z20_set_rx_gain_mode(uint32_t mode) {
    if (!phy || mode>3) return -EINVAL;
    int ret=ad9361_set_rx_gain_control_mode(phy,RX1,mode);
    if (!ret) ret=ad9361_set_rx_gain_control_mode(phy,RX2,mode);
    return ret;
}
int z20_bist_loopback(int enable) {
    if (!phy || (enable!=0 && enable!=1)) return -EINVAL;
    int ret=ad9361_tx_mute(phy,1);
    if (!ret) ret=ad9361_set_en_state_machine_mode(phy,ENSM_MODE_ALERT);
    if (!ret) ret=ad9361_bist_prbs(phy,BIST_DISABLE);
    if (!ret) ret=ad9361_bist_loopback(phy,enable);
    phy->pdata->fdd=enable ? true : false;
    if (!ret) ret=ad9361_set_en_state_machine_mode(phy,enable ? ENSM_MODE_FDD : ENSM_MODE_ALERT);
    if (ret) z20_platform_hold_reset();
    return ret;
}
int z20_read_register(uint32_t address) {
    if (!phy || address > 0x3ff) return -EINVAL;
    return ad9361_spi_read(phy->spi, address);
}
int z20_get_sample_rate(uint32_t *rate) {
    return phy ? ad9361_get_rx_sampling_freq(phy, rate) : -ENODEV;
}
int z20_get_ensm_mode(uint32_t *mode) {
    return phy ? ad9361_get_en_state_machine_mode(phy, mode) : -ENODEV;
}
int z20_get_tx_attenuation(uint8_t channel, uint32_t *mdb) {
    return phy ? ad9361_get_tx_attenuation(phy, channel, mdb) : -ENODEV;
}
int z20_rx_test_tone(int enable) {
    if (!phy || (enable != 0 && enable != 1)) return -EINVAL;
    /* RX injection only. Tone code0 is sample-rate/32, level12 means -12dB. */
    int ret = ad9361_tx_mute(phy, 1);
    if (!ret) ret = ad9361_set_en_state_machine_mode(phy, enable ? ENSM_MODE_RX : ENSM_MODE_ALERT);
    if (!ret) ret = ad9361_bist_tone(phy, enable ? BIST_INJ_RX : BIST_DISABLE, 0, 12, 0);
    if (ret) z20_platform_hold_reset();
    return ret;
}
int z20_configure_receive(uint64_t lo_hz, uint32_t rate_hz, uint32_t bandwidth_hz) {
    if (!phy || lo_hz < 70000000ULL || lo_hz > 6000000000ULL ||
        rate_hz < 2083334 || rate_hz > 61440000 ||
        bandwidth_hz < 200000 || bandwidth_hz > rate_hz || bandwidth_hz > 56000000) return -EINVAL;
    int ret = ad9361_tx_mute(phy, 1);
    if (!ret) ret = ad9361_set_en_state_machine_mode(phy, ENSM_MODE_ALERT);
    if (!ret) ret = ad9361_bist_loopback(phy, 0);
    if (!ret) ret = ad9361_bist_prbs(phy, BIST_DISABLE);
    if (!ret) ret = ad9361_bist_tone(phy, BIST_DISABLE, 0, 0, 0);
    if (!ret) ret = ad9361_set_rx_sampling_freq(phy, rate_hz);
    if (!ret) ret = ad9361_set_rx_lo_freq(phy, lo_hz);
    if (!ret) ret = ad9361_set_rx_rf_bandwidth(phy, bandwidth_hz);
    if (!ret) ret = ad9361_set_rx_gain_control_mode(phy, RX1, RF_GAIN_SLOWATTACK_AGC);
    if (!ret) ret = ad9361_set_rx_gain_control_mode(phy, RX2, RF_GAIN_SLOWATTACK_AGC);
    if (!ret) ret = ad9361_set_en_state_machine_mode(phy, ENSM_MODE_RX);
    if (ret) z20_platform_hold_reset();
    return ret;
}
int z20_start_receive(uint64_t lo_hz) {
    return z20_configure_receive(lo_hz, 30720000, 24000000);
}
int z20_get_rx_lo(uint64_t *hz) {
    return phy ? ad9361_get_rx_lo_freq(phy, hz) : -ENODEV;
}
int z20_get_rx_gain(uint8_t channel, int32_t *db) {
    if (!phy || channel > RX2 || !db) return -EINVAL;
    return ad9361_get_rx_rf_gain(phy, channel, db);
}
int z20_get_rx_rssi(uint8_t channel, int32_t *mdb) {
    if (!phy || channel > RX2 || !mdb) return -EINVAL;
    struct rf_rssi rssi = {0};
    int ret = ad9361_get_rx_rssi(phy, channel, &rssi);
    if (ret) return ret;
    if (!rssi.multiplier) return -EIO;
    *mdb = -(int64_t)rssi.symbol * 1000 / rssi.multiplier;
    return 0;
}
int z20_check_rx_prbs(uint32_t duration_ms, uint32_t *channel_status) {
    if (!phy || !channel_status || duration_ms < 10 || duration_ms > 2000) return -EINVAL;
    uint32_t saved[4];
    int ret = ad9361_tx_mute(phy, 1);
    for (unsigned ch = 0; ch < 4; ++ch) {
        axi_adc_read(phy->rx_adc, AXI_ADC_REG_CHAN_CNTRL_3(ch), &saved[ch]);
        axi_adc_set_pnsel(phy->rx_adc, ch, AXI_ADC_PN9);
    }
    if (!ret) ret = ad9361_set_en_state_machine_mode(phy, ENSM_MODE_RX);
    if (!ret) ret = ad9361_bist_prbs(phy, BIST_INJ_RX);
    if (!ret) {
        no_os_mdelay(20);
        for (unsigned ch = 0; ch < 4; ++ch)
            axi_adc_write(phy->rx_adc, AXI_ADC_REG_CHAN_STATUS(ch), AXI_ADC_PN_ERR | AXI_ADC_PN_OOS);
        no_os_mdelay(duration_ms);
        for (unsigned ch = 0; ch < 4; ++ch) {
            axi_adc_read(phy->rx_adc, AXI_ADC_REG_CHAN_STATUS(ch), &channel_status[ch]);
            if (channel_status[ch] & (AXI_ADC_PN_ERR | AXI_ADC_PN_OOS)) ret = -EIO;
        }
    }
    ad9361_bist_prbs(phy, BIST_DISABLE);
    for (unsigned ch = 0; ch < 4; ++ch)
        axi_adc_write(phy->rx_adc, AXI_ADC_REG_CHAN_CNTRL_3(ch), saved[ch]);
    ad9361_set_en_state_machine_mode(phy, ENSM_MODE_ALERT);
    if (ret) z20_platform_hold_reset();
    return ret;
}

/* Finite RX-only PN9 scan. Restore calibration; never enable or unmute TX. */
int z20_scan_rx_delays(uint32_t duration_ms, uint32_t *status) {
    if (!phy || !status || duration_ms < 10 || duration_ms > 100) return -EINVAL;
    int original = ad9361_spi_read(phy->spi, REG_RX_CLOCK_DATA_DELAY);
    if (original < 0) return original;
    uint32_t controls[4];
    for (unsigned ch=0; ch<4; ++ch)
        axi_adc_read(phy->rx_adc, AXI_ADC_REG_CHAN_CNTRL_3(ch), &controls[ch]);
    int ret = ad9361_tx_mute(phy, 1);
    if (!ret) ret = ad9361_bist_loopback(phy, 0);
    for (unsigned ch=0; ch<4 && !ret; ++ch)
        ret = axi_adc_set_pnsel(phy->rx_adc, ch, AXI_ADC_PN9);
    if (!ret) ret = ad9361_bist_prbs(phy, BIST_INJ_RX);
    for (unsigned clock=0; clock<16 && !ret; ++clock) {
        for (unsigned data=0; data<16 && !ret; ++data) {
            ret = ad9361_set_en_state_machine_mode(phy, ENSM_MODE_ALERT);
            if (!ret) ret = ad9361_spi_write(phy->spi, REG_RX_CLOCK_DATA_DELAY,
                                           DATA_CLK_DELAY(clock)|RX_DATA_DELAY(data));
            if (!ret) ret = ad9361_set_en_state_machine_mode(phy, ENSM_MODE_RX);
            if (ret) break;
            no_os_mdelay(5);
            for (unsigned ch=0; ch<4; ++ch)
                axi_adc_write(phy->rx_adc, AXI_ADC_REG_CHAN_STATUS(ch), AXI_ADC_PN_ERR|AXI_ADC_PN_OOS);
            no_os_mdelay(duration_ms);
            uint32_t combined=0, value=0;
            for (unsigned ch=0; ch<4; ++ch) {
                axi_adc_read(phy->rx_adc, AXI_ADC_REG_CHAN_STATUS(ch), &value);
                combined |= value & (AXI_ADC_PN_ERR|AXI_ADC_PN_OOS);
            }
            axi_adc_read(phy->rx_adc, AXI_ADC_REG_STATUS, &value);
            if (!(value & 1)) combined |= 0x100;
            status[clock*16+data]=combined;
        }
    }
    ad9361_set_en_state_machine_mode(phy, ENSM_MODE_ALERT);
    ad9361_spi_write(phy->spi, REG_RX_CLOCK_DATA_DELAY, original);
    ad9361_bist_prbs(phy, BIST_DISABLE);
    for (unsigned ch=0; ch<4; ++ch)
        axi_adc_write(phy->rx_adc, AXI_ADC_REG_CHAN_CNTRL_3(ch), controls[ch]);
    if (ad9361_spi_read(phy->spi, REG_RX_CLOCK_DATA_DELAY) != original) ret=-EIO;
    if (ret) z20_platform_hold_reset();
    return ret;
}
