"""Bounded double-buffered RGB332 display for the J22 SSD1963 overlay."""
import time
import numpy as np

WIDTH, HEIGHT, PAGE_BYTES = 400, 240, 131072


def rgb332(image):
    rgb = np.asarray(image)
    if rgb.shape != (HEIGHT, WIDTH, 3) or rgb.dtype != np.uint8:
        raise ValueError('Expected a 400x240 uint8 RGB image')
    return ((rgb[:, :, 0] & 0xe0) | ((rgb[:, :, 1] >> 3) & 0x1c)
            | (rgb[:, :, 2] >> 6)).astype(np.uint8)


class LcdFramebuffer:
    def __init__(self, memory, control):
        self.memory, self.control = memory, control
        if memory.length < 2*PAGE_BYTES:
            raise ValueError('LCD requires a 256KiB memory aperture')
        self.status()

    def status(self):
        value = int(self.control.read(8))
        if value >> 16 != 0x4c43:
            raise RuntimeError('LCD controller signature mismatch')
        return dict(active_page=value & 1, ready=bool(value & 2),
                    frame_gray=(value >> 2) & 0x3fff)

    def wait_active(self, page, timeout_s):
        deadline = time.monotonic()+timeout_s
        while time.monotonic() < deadline:
            a = self.status()
            if a['ready'] and a['active_page'] == page:
                time.sleep(.001)
                b = self.status()
                if b['ready'] and b['active_page'] == page:
                    return b
            time.sleep(.002)
        raise TimeoutError('LCD frame-boundary acknowledgement timed out')

    def present(self, image, timeout_s=3):
        pixels = np.asarray(image)
        if pixels.shape != (HEIGHT, WIDTH) or pixels.dtype != np.uint8 or timeout_s <= 0:
            raise ValueError('Expected a 400x240 RGB332 frame and positive timeout')
        requested = int(self.control.read(0)) & 1
        self.wait_active(requested, timeout_s)
        target = 1-requested
        offset = target*PAGE_BYTES
        self.memory.write(offset, np.ascontiguousarray(pixels).tobytes())
        self.memory.read(offset+pixels.size-4)  # drain writes before requesting page swap
        self.control.write(0, target)
        return self.wait_active(target, timeout_s)
