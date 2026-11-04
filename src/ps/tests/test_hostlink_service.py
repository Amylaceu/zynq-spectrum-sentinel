"""Real loopback sockets exercise framing, web streaming and bounded ownership."""
import json
import socket
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentinel.app.hostlink import Hostlink
from sentinel.app.hostlink_protocol import Decoder, encode


def service(**kwargs):
    return Hostlink('127.0.0.1', {'bit_sha256': 'test-only'}, allow_loopback=True,
                    tcp_port=0, http_port=0, **kwargs)


def command(seq, name, args=None, **extra):
    return encode(dict(type='command', seq=seq, t_mono=0., len=0,
                       command=name, args=args or {}, **extra))


def until(predicate, seconds=2):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.005)
    raise AssertionError('Timed out')


def connect(server):
    client = socket.create_connection(('127.0.0.1', server.tcp_port), timeout=2)
    decoder = Decoder()
    frames = decoder.feed(client.recv(65536))
    assert frames[0][0]['protocol'] == 'hostlink/1'
    return client, decoder


def test_owner_command_and_binary_publish():
    with service() as server:
        client, decoder = connect(server)
        with client:
            client.sendall(command(0, 'set_page', {'page': 'TGT'}))
            request = until(server.poll)
            assert request[2:] == ('set_page', {'page': 'TGT'})
            # No implicit acceptance: caller executes then explicitly replies.
            server.reply(request, applied=True)
            until(lambda: decoder.feed(client.recv(65536)))
            server.publish('iq', b'\0'*4096, sample_rate_hz=480000)
            header, payload = until(lambda: decoder.feed(client.recv(65536)))[0]
            assert header['type'] == 'iq' and len(payload) == 4096


def test_rejections_do_not_reach_owner_or_expose_token():
    with service(token='secret-test') as server:
        client, decoder = connect(server)
        with client:
            for seq, name in enumerate(('tx', 'set_attenuation', 'shell', 'ping')):
                client.sendall(command(seq, name, token='wrong'))
            until(lambda: server.stats['rejected'] == 4)
            assert server.poll() is None
            assert 'wrong' not in json.dumps(server.summary())
            client.sendall(command(4, 'ping', token='secret-test'))
            assert until(server.poll)[2] == 'ping'


def test_three_clients_limit_and_ten_reconnects():
    with service() as server:
        clients = [connect(server)[0] for _ in range(3)]
        try:
            with socket.create_connection(('127.0.0.1', server.tcp_port), timeout=2) as extra:
                assert extra.recv(1) == b''
        finally:
            for client in clients:
                client.close()
        until(lambda: not server.connected)
        for _ in range(10):
            client, _ = connect(server)
            client.close()
            until(lambda: not server.connected)
        assert server._error is None


def test_http_and_sse_real_payload():
    with service() as server:
        with urlopen('http://127.0.0.1:%d/' % server.http_port, timeout=2) as response:
            assert b'Spectrum Sentinel' in response.read()
        with urlopen('http://127.0.0.1:%d/events' % server.http_port, timeout=2) as response:
            assert response.readline() == b': ready\n'
            assert response.readline() == b'\n'
            server.publish('detections', targets=[dict(frequency_hz=95800000)])
            value = json.loads(response.readline().decode().removeprefix('data: '))
            assert value['targets'][0]['frequency_hz'] == 95800000


def test_binding_and_startup_failure_clean_up():
    for address in ('0.0.0.0', '8.8.8.8', '224.0.0.1', '127.0.0.1'):
        with pytest.raises(ValueError):
            Hostlink(address, {})
    with service() as first:
        other = Hostlink('127.0.0.1', {}, allow_loopback=True,
                         tcp_port=first.tcp_port, http_port=0)
        with pytest.raises(RuntimeError):
            other.start()
        assert not other._thread.is_alive()


def test_slow_client_does_not_block_producer():
    with service() as server:
        client, _ = connect(server)
        with client:
            start = time.monotonic()
            for _ in range(800):
                server.publish('iq', b'\0'*4096)
            assert time.monotonic()-start < 2
            assert server._out.qsize() <= 64
            assert server.stats['max_queue_bytes'] <= 2*1024*1024
            assert server._error is None
