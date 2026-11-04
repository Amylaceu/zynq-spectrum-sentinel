"""hostlink/1 framing, bounded per-client buffering and command validation.

Python 3.8 standard library only. No sockets, hardware or threads on import.
This module validates requests; only the acquisition owner may execute them.
"""
from collections import deque
import hmac
import json
import math

VERSION = 'hostlink/1'
MAX_HEADER = 16384
MAX_PAYLOAD = 1024*1024
MAX_QUEUE = 2*1024*1024
TYPES = frozenset(('hello', 'spectrum', 'detections', 'amc', 'iq', 'telemetry',
                   'event', 'demo', 'command', 'reply', 'error',
                   'ui_frame', 'pl_frame', 'ui_state', 'audio', 'file'))
LOSSY = frozenset(('spectrum', 'iq', 'pl_frame', 'ui_frame', 'audio'))


class ProtocolError(ValueError):
    pass


def checked_header(header):
    if (not isinstance(header, dict) or not isinstance(header.get('type'), str)
            or header['type'] not in TYPES):
        raise ProtocolError('Unknown message type')
    if type(header.get('seq')) is not int or header['seq'] < 0:
        raise ProtocolError('Invalid sequence')
    stamp = header.get('t_mono')
    if type(stamp) not in (float, int) or not math.isfinite(stamp) or stamp < 0:
        raise ProtocolError('Invalid monotonic timestamp')
    if type(header.get('len')) is not int or not 0 <= header['len'] <= MAX_PAYLOAD:
        raise ProtocolError('Invalid payload length')
    return header


def encode(header, payload=b''):
    checked_header(header)
    if not isinstance(payload, bytes) or len(payload) != header['len']:
        raise ProtocolError('Payload length/type mismatch')
    try:
        prefix = json.dumps(header, separators=(',', ':'), ensure_ascii=True,
                            allow_nan=False).encode('ascii')+b'\n'
    except (ValueError, TypeError) as error:
        raise ProtocolError('Invalid JSON header') from error
    if len(prefix) > MAX_HEADER:
        raise ProtocolError('Header too large')
    return prefix+payload


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError('Duplicate JSON key')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ProtocolError('Non-finite JSON constant')


class Decoder:
    def __init__(self):
        self.buffer = bytearray()
        self.header = None
        self.last_seq = -1

    def feed(self, data):
        if len(self.buffer)+len(data) > MAX_QUEUE:
            raise ProtocolError('Input buffer limit')
        self.buffer.extend(data)
        output = []
        while True:
            if self.header is None:
                index = self.buffer.find(b'\n')
                if index < 0:
                    if len(self.buffer) >= MAX_HEADER:
                        raise ProtocolError('Header limit')
                    break
                if index+1 > MAX_HEADER:
                    raise ProtocolError('Header limit')
                try:
                    header = json.loads(bytes(self.buffer[:index]).decode('ascii'),
                                        object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant)
                    checked_header(header)
                except (ValueError, UnicodeError, TypeError) as error:
                    raise ProtocolError('Invalid header') from error
                if header['seq'] <= self.last_seq:
                    raise ProtocolError('Non-increasing sequence')
                self.header = header
                del self.buffer[:index+1]
            count = self.header['len']
            if len(self.buffer) < count:
                break
            payload = bytes(self.buffer[:count])
            del self.buffer[:count]
            self.last_seq = self.header['seq']
            output.append((self.header, payload))
            self.header = None
        return output


class ClientQueue:
    """Never block a producer; a client unable to retain control is disconnected.

    Dequeued packets are owned by the network sender. Its single partial packet
    must remain within this same byte budget until acknowledged by socket.send.
    """
    def __init__(self, limit=MAX_QUEUE):
        if type(limit) is not int or not 128 <= limit <= MAX_QUEUE:
            raise ValueError('Invalid queue budget')
        self.limit, self.pending, self.bytes = limit, deque(), 0
        self.dropped = 0
        self.partial = False

    def push(self, kind, packet):
        if kind not in TYPES or not isinstance(packet, bytes) or len(packet) > self.limit:
            raise ProtocolError('Packet exceeds client budget')
        while self.bytes+len(packet) > self.limit:
            victim = next((i for i, (name, _) in enumerate(self.pending)
                           if name in LOSSY and not (i == 0 and self.partial)), None)
            if victim is None:
                if kind in LOSSY:
                    self.dropped += 1
                    return False
                raise BufferError('Slow client cannot retain control messages; disconnect')
            _, old = self.pending[victim]
            del self.pending[victim]
            self.bytes -= len(old)
            self.dropped += 1
        self.pending.append((kind, packet))
        self.bytes += len(packet)
        return True

    def peek(self):
        return self.pending[0][1] if self.pending else None

    def consume(self, count):
        if not self.pending or type(count) is not int or not 0 < count <= len(self.pending[0][1]):
            raise ValueError('Invalid send progress')
        kind, packet = self.pending[0]
        if count == len(packet):
            self.pending.popleft()
            self.partial = False
        else:
            self.pending[0] = (kind, packet[count:])
            self.partial = True
        self.bytes -= count


def validate_command(header, mode, token=None):
    checked_header(header)
    if header['type'] != 'command' or header['len'] != 0:
        raise ProtocolError('Expected command without binary payload')
    if token is not None:
        supplied = header.get('token')
        if not isinstance(supplied, str) or not hmac.compare_digest(supplied.encode(), token.encode()):
            raise ProtocolError('Authentication failed')
    name = header.get('command')
    args = header.get('args', {})
    if not isinstance(args, dict):
        raise ProtocolError('Command arguments must be an object')
    expected = {'ping': (), 'get_status': (), 'snapshot': (), 'stop': (),
                'select_target': ('key',), 'set_page': ('page',),
                'set_lo': ('hz',), 'listen': ('mhz',), 'click': ('x', 'y'),
                'listen_target': ('key',), 'scene': ('id',),
                'feature': ('id', 'action', 'mode', 'alpha'),
                'application': ('id', 'action', 'station_hz', 'antenna_2g4')}
    if (not isinstance(name, str) or name not in expected or set(args) != set(expected[name])
            or set(header)-{'type', 'seq', 't_mono', 'len', 'command', 'args', 'token'}):
        raise ProtocolError('Command/arguments not in whitelist')
    if name in ('select_target', 'listen_target') and (type(args['key']) is not int or args['key'] < 0):
        raise ProtocolError('Invalid target key')
    if name == 'scene':
        from .resident import SCENES
        if mode != 'resident' or args['id'] not in SCENES:
            raise ProtocolError('Scene requires resident mode and a preset ID')
    if name == 'feature':
        if (mode != 'resident' or args['id'] not in tuple('F%d' % i for i in range(1, 11))
                or args['action'] not in ('start', 'stop') or args['mode'] not in ('CA', 'GO', 'SO')
                or type(args['alpha']) is not int or not 256 <= args['alpha'] <= 8192):
            raise ProtocolError('Invalid bounded receive-only feature request')
    if name == 'application':
        if (mode != 'resident' or args['id'] not in ('F0', 'F8', 'F11', 'F12', 'F13', 'F14')
                or args['action'] not in ('start', 'stop', 'search', 'record', 'record_stop')
                or args['action'] in ('search', 'record', 'record_stop') and args['id'] != 'F8'
                or type(args['antenna_2g4']) is not bool
                or type(args['station_hz']) is not int
                or args['station_hz'] != 0 and not 87500000 <= args['station_hz'] <= 108000000
                or args['id'] == 'F14' and args['action'] == 'start' and not args['antenna_2g4']):
            raise ProtocolError('Invalid bounded application request')
    if name == 'click' and any(type(args[k]) is not int or not 0 <= args[k] < limit
                               for k, limit in (('x', 800), ('y', 480))):
        raise ProtocolError('Click outside LCD physical coordinates')
    if name == 'set_page' and args['page'] not in ('SIG', 'TGT', 'STAT'):
        raise ProtocolError('Invalid UI page')
    if name in ('set_lo', 'listen'):
        value = args['hz'] if name == 'set_lo' else args['mhz']
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ProtocolError('Frequency must be finite')
        if name == 'set_lo' and (mode != 'monitor' or not 70000000 <= value <= 2700000000):
            raise ProtocolError('LO is only adjustable in receive monitor mode')
        if name == 'listen' and (mode not in ('monitor', 'listen') or not 87.5 <= value <= 108):
            raise ProtocolError('Listening only accepts receive FM mode/band')
    return name, dict(args)
