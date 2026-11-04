"""Processing-clock contracts for accepted legacy and candidate overlays.

Do not reinterpret historical v1b/v1d measurements as 100 MHz. A caller must
select the clock belonging to its bitstream when converting cycles to time.
"""

LEGACY_DSP_CLK_HZ = 150_000_000
DSP_CLK_HZ = 100_000_000  # sentinel_v2_100m candidate only


def clock_hz_for_image(image):
    if image == 'sentinel_v2_100m':
        return DSP_CLK_HZ
    if image in ('sentinel_v1', 'sentinel_v1b', 'sentinel_v1d', 'sentinel_y3'):
        return LEGACY_DSP_CLK_HZ
    raise ValueError('Unknown bitstream clock contract: ' + str(image))
