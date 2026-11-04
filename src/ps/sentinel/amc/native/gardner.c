/* Optional CPU-only timing recovery. No device, RF or FPGA access.
 * Build without fast-math or contraction: reference operation order matters.
 * Interleaved complex128 arrays are passed explicitly; no NumPy C API. */
#include <math.h>
#include <stddef.h>

int sentinel_gardner_abi(void) { return 1; }

static void interpolate(const double *x, double t, double *real, double *imag) {
    size_t i = (size_t)t;
    double fraction = t - (double)i;
    *real = x[2*i] * (1.0-fraction) + x[2*(i+1)] * fraction;
    *imag = x[2*i+1] * (1.0-fraction) + x[2*(i+1)+1] * fraction;
}

/* Returns symbol count, or a negative error. Bounds checked before every read. */
int sentinel_gardner(const double *x, size_t n, double sps, double phase,
                     double *out, size_t capacity) {
    if (!x || !out || n < 256 || n > 1048576 || capacity < 1 ||
        !isfinite(sps) || sps < 4.0 || sps > 16.0 ||
        !isfinite(phase) || phase < 0.0 || phase >= sps) return -1;
    for (size_t i=0; i<2*n; ++i) if (!isfinite(x[i])) return -2;
    double t = 8.0*sps + phase, omega = sps;
    size_t count = 0;
    while (t + omega/2.0 + 1.0 < (double)n - 8.0*sps) {
        double early_t=t-omega/2.0, late_t=t+omega/2.0;
        if (early_t < 0.0 || late_t+1.0 >= (double)n || count>=capacity) return -3;
        double er,ei,cr,ci,lr,li;
        interpolate(x,early_t,&er,&ei);
        interpolate(x,t,&cr,&ci);
        interpolate(x,late_t,&lr,&li);
        double error=(lr-er)*cr + (li-ei)*ci;
        if (error>2.0) error=2.0;
        if (error< -2.0) error= -2.0;
        out[2*count]=cr; out[2*count+1]=ci; ++count;
        omega=omega+0.0002*error;
        if (omega>1.05*sps) omega=1.05*sps;
        if (omega<0.95*sps) omega=0.95*sps;
        t += omega+0.02*error;
    }
    return (int)count;
}
