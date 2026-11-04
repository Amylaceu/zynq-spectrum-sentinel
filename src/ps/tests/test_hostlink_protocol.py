import json
import struct

import pytest

from src.ps.sentinel.app.hostlink_protocol import (
    ClientQueue, Decoder, MAX_HEADER, MAX_QUEUE, ProtocolError, encode, validate_command)


def message(kind='spectrum', seq=1, payload=b''):
    return dict(type=kind, seq=seq, t_mono=12.3, len=len(payload))


def test_binary_payload_fragmentation_and_multiple_messages():
    payload = struct.pack('<3h', -32768, 10, 32767)
    wire = encode(message(payload=payload), payload)+encode(message('telemetry', 2))
    decoder = Decoder()
    result = []
    for byte in wire:
        result.extend(decoder.feed(bytes([byte])))
    assert len(result) == 2 and result[0][1] == payload
    assert struct.unpack('<3h', result[0][1]) == (-32768, 10, 32767)
    assert not decoder.buffer


@pytest.mark.parametrize('wire', [b'{}\n', b'X'*MAX_HEADER,
    b'{"type":"iq","seq":1,"seq":2,"t_mono":1,"len":0}\n',
    b'{"type":"iq","seq":1,"t_mono":NaN,"len":0}\n',
    b'{"type":"iq","seq":1,"t_mono":1,"len":-1}\n'])
def test_invalid_or_unbounded_headers_are_rejected(wire):
    with pytest.raises(ProtocolError):
        Decoder().feed(wire)


def test_replayed_sequence_is_rejected():
    decoder = Decoder()
    packet = encode(message('hello'))
    decoder.feed(packet)
    with pytest.raises(ProtocolError, match='sequence'):
        decoder.feed(packet)


def test_slow_clients_drop_only_old_data_and_keep_control():
    queue = ClientQueue(128)
    queue.push('event', b'e'*30)
    queue.push('spectrum', b'a'*70)
    queue.push('iq', b'b'*70)
    assert queue.bytes == 100 and queue.dropped == 1
    assert queue.peek() == b'e'*30
    queue.consume(30)
    assert queue.peek() == b'b'*70


def test_partially_sent_packet_is_never_dropped_or_reordered():
    queue = ClientQueue(128)
    queue.push('spectrum', b'a'*120)
    queue.consume(10)
    assert not queue.push('iq', b'b'*120)
    assert queue.peek() == b'a'*110 and queue.bytes == 110
    with pytest.raises(BufferError):
        queue.push('event', b'e'*30)
    queue.consume(110)
    assert queue.peek() is None and not queue.partial


@pytest.mark.parametrize('name', ['tx', 'set_tx_atten', 'shell', 'reboot', 'demo_B', 'set_guard'])
def test_transmission_or_arbitrary_commands_are_always_rejected(name):
    header = dict(message('command'), command=name, args={})
    with pytest.raises(ProtocolError):
        validate_command(header, 'monitor')


@pytest.mark.parametrize('name,args,mode', [
    ('set_lo', {'hz': 2450000000}, 'demo'), ('set_lo', {'hz': 69999999}, 'monitor'),
    ('set_lo', {'hz': float('inf')}, 'monitor'), ('listen', {'mhz': 433.92}, 'monitor'),
    ('select_target', {'key': True}, 'monitor'), ('set_page', {'page': 'TX'}, 'monitor'),
    ('ping', {'shell': 'anything'}, 'monitor')])
def test_bad_receive_requests_are_not_promoted_to_hardware_commands(name, args, mode):
    with pytest.raises(ProtocolError):
        validate_command(dict(message('command'), command=name, args=args), mode)


def test_whitelisted_commands_and_optional_token():
    header = dict(message('command'), command='set_lo', args={'hz': 96050000}, token='test-only')
    assert validate_command(header, 'monitor', token='test-only') == ('set_lo', {'hz': 96050000})
    with pytest.raises(ProtocolError, match='Authentication'):
        validate_command(header, 'monitor', token='different-test-token')
