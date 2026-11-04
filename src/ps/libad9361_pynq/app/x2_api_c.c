/* Independent X2 library: retain the accepted muted-RX API and add readback.
 * Including the implementation keeps its private phy in this translation
 * unit without changing the frozen v1 library or third-party sources. */
#include "ad9361_api_c.c"

int z20_x2_get_rx_bandwidth(uint32_t *hz)
{
    if (!phy || !hz)
        return -ENODEV;
    return ad9361_get_rx_rf_bandwidth(phy, hz);
}
