"""Bounded hostlink/1 network worker. Hardware is owned by its caller.

One selector thread serves TCP and HTTP/SSE. Producers never send sockets;
commands are validated here and executed only when the owner polls them.
Python 3.8 standard library only, no import-time network activity.
"""
from collections import deque
import ipaddress
import json
import queue
import selectors
import socket
import threading
import time
from urllib.parse import urlsplit

from .hostlink_protocol import (VERSION, MAX_QUEUE, ClientQueue, Decoder,
                               ProtocolError, encode, validate_command)


PAGE = b'''<!doctype html><meta charset="utf-8"><title>Spectrum Sentinel</title>
<style>body{background:#101820;color:#edf6ff;font:16px monospace;margin:24px}
canvas{width:100%;height:300px;background:#071018}td,th{padding:6px;text-align:left}
#state{color:#57ded5}</style><h1>Spectrum Sentinel</h1><p id="state">Connecting</p>
<canvas id="plot" width="1024" height="300"></canvas><p id="info"></p>
<table><thead><tr><th>MHz</th><th>kHz</th><th>Raw power</th><th>Class</th></tr></thead>
<tbody id="targets"></tbody></table><script>
const es=new EventSource('/events');const c=document.querySelector('canvas'),g=c.getContext('2d');
es.onopen=()=>state.textContent='LIVE / receive telemetry';
es.onerror=()=>state.textContent='Disconnected / retrying';
es.onmessage=e=>{let d=JSON.parse(e.data);if(d.type==='spectrum'){
let a=d.values,lo=Math.min(...a)/100,hi=Math.max(...a)/100;g.clearRect(0,0,1024,300);
g.strokeStyle='#57ded5';g.beginPath();a.forEach((v,i)=>{let y=280-(v/100-lo)*260/Math.max(1,hi-lo);
i?g.lineTo(i,y):g.moveTo(i,y)});g.stroke();
info.textContent='Relative raw power (dB re integer 1), '+(d.lo_hz/1e6).toFixed(3)+' MHz';}
if(d.type==='detections'){targets.replaceChildren();for(let t of d.targets){let r=document.createElement('tr');
for(let v of [(t.frequency_hz/1e6).toFixed(3),(t.bandwidth_hz/1e3).toFixed(1),t.power,t.label]){
let cell=document.createElement('td');cell.textContent=v;r.appendChild(cell)}targets.appendChild(r)}}};
</script>'''


class Hostlink:
    def __init__(self, address, hello, mode='monitor', token=None, tcp_port=9000,
                 http_port=8080, allow_loopback=False):
        ip = ipaddress.ip_address(address)
        if (ip.version != 4 or not ip.is_private or ip.is_unspecified or ip.is_multicast
                or ip.is_link_local or (ip.is_loopback and not allow_loopback)):
            raise ValueError('Explicit LAN IPv4 address required')
        self.address, self.mode, self.token = address, mode, token
        self.hello = dict(hello, protocol=VERSION)
        self.tcp_port, self.http_port = tcp_port, http_port
        self._out = queue.Queue(maxsize=64)
        self._commands = queue.Queue(maxsize=32)
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = None
        self._error = None
        self._seq = self._client_id = 0
        self._clients = {}
        self._closed_drops = 0
        self._selector = None
        self.rejections = deque(maxlen=128)
        self.stats = dict(producer_drops=0, client_drops=0, connections=0,
                          rejected=0, accepted_commands=0, cpu_s=0., max_queue_bytes=0)
        self.status = {}

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.close()

    def start(self):
        if self._thread is not None:
            raise RuntimeError('Service already started')
        self._thread = threading.Thread(target=self._run, name='sentinel-hostlink', daemon=True)
        self._thread.start()
        if not self._ready.wait(5):
            self.close()
            raise TimeoutError('hostlink startup timed out')
        if self._error is not None:
            self.close()
            raise RuntimeError('hostlink startup failed') from self._error
        return self

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(3)
            if self._thread.is_alive():
                raise RuntimeError('hostlink worker did not stop')

    @property
    def connected(self):
        return any(c['kind'] in ('tcp', 'sse') for c in list(self._clients.values()))

    def publish(self, kind, payload=b'', **fields):
        """Bounded nonblocking handoff, never waits for a client or acquisition."""
        # Validate before queueing; packet size also bounds producer memory.
        encode(dict(fields, type=kind, seq=0, t_mono=time.monotonic(), len=len(payload)), payload)
        if len(payload) > 65536:
            raise ValueError('Runtime publication exceeds 64KiB budget')
        try:
            self._out.put_nowait((None, kind, payload, fields))
            return True
        except queue.Full:
            self.stats['producer_drops'] += 1
            return False

    def poll(self):
        try:
            return self._commands.get_nowait()
        except queue.Empty:
            return None

    def reply(self, request, ok=True, **fields):
        client, seq, _, _ = request
        try:
            self._out.put_nowait((client, 'reply', b'', dict(fields, request_seq=seq, ok=ok)))
        except queue.Full:
            self.stats['producer_drops'] += 1

    def summary(self):
        value = dict(self.stats, connected_clients=sum(
            c['kind'] in ('tcp', 'sse') for c in list(self._clients.values())),
            thread_error=repr(self._error) if self._error else None,
            rejections=list(self.rejections), tcp_port=self.tcp_port, http_port=self.http_port)
        return value

    def _packet(self, kind, payload=b'', **fields):
        self._seq += 1
        return encode(dict(fields, type=kind, seq=self._seq,
                           t_mono=time.monotonic(), len=len(payload)), payload)

    def _drop(self, client):
        if self._clients.pop(client['id'], None) is not None:
            self._closed_drops += client['queue'].dropped
        try:
            self._selector.unregister(client['socket'])
        except (KeyError, ValueError):
            pass
        client['socket'].close()

    def _enqueue(self, client, kind, packet):
        try:
            client['queue'].push(kind, packet)
            self.stats['max_queue_bytes'] = max(self.stats['max_queue_bytes'], client['queue'].bytes)
            self._selector.modify(client['socket'], selectors.EVENT_READ | selectors.EVENT_WRITE, client)
        except (BufferError, ProtocolError):
            self._drop(client)

    def _accept(self, listener, kind):
        connection, _ = listener.accept()
        connection.setblocking(False)
        if len(self._clients) >= 3:
            connection.close()
            return
        self._client_id += 1
        client = dict(id=self._client_id, socket=connection, kind=kind, queue=ClientQueue(),
                      decoder=Decoder(), input=bytearray(), close=False, sse_last=0.,
                      accepted=time.monotonic())
        self._clients[client['id']] = client
        self.stats['connections'] += 1
        self._selector.register(connection, selectors.EVENT_READ, client)
        if kind == 'tcp':
            self._enqueue(client, 'hello', self._packet('hello', **self.hello))

    def _reject(self, client, header, reason):
        self.stats['rejected'] += 1
        # Never retain the request/token or untrusted argument values in logs.
        self.rejections.append(dict(t_mono=time.monotonic(), reason=str(reason)[:160]))
        self._enqueue(client, 'error', self._packet('error', request_seq=header.get('seq'),
                                                  error=str(reason)[:160]))

    def _read(self, client):
        data = client['socket'].recv(65536)
        if not data:
            self._drop(client)
            return
        if client['kind'] == 'tcp':
            try:
                frames = client['decoder'].feed(data)
            except ProtocolError as error:
                self.stats['rejected'] += 1
                self.rejections.append(dict(t_mono=time.monotonic(), reason=str(error)))
                self._drop(client)
                return
            for header, payload in frames:
                try:
                    command, args = validate_command(header, self.mode, self.token)
                    request = (client['id'], header['seq'], command, args)
                    self._commands.put_nowait(request)
                    self.stats['accepted_commands'] += 1
                except (ProtocolError, queue.Full) as error:
                    self._reject(client, header, 'Command queue full' if isinstance(error, queue.Full) else error)
        elif client['kind'] == 'http':
            client['input'].extend(data)
            if len(client['input']) > 8192:
                self._drop(client)
                return
            if b'\r\n\r\n' not in client['input']:
                return
            line = bytes(client['input']).split(b'\r\n', 1)[0].decode('ascii', 'replace').split()
            client['input'].clear()
            if len(line) != 3 or line[0] != 'GET':
                self._drop(client)
                return
            # With a token, web is deliberately disabled (no token in URL/logs).
            if self.token is not None:
                response = b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
                client['close'] = True
            elif urlsplit(line[1]).path == '/events':
                client['kind'] = 'sse'
                response = (b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                            b'Cache-Control: no-cache\r\nConnection: keep-alive\r\n\r\n: ready\n\n')
            else:
                body = PAGE if line[1] == '/' else b'Not found'
                code = b'200 OK' if line[1] == '/' else b'404 Not Found'
                response = (b'HTTP/1.1 '+code+b'\r\nContent-Type: text/html; charset=utf-8\r\n'
                            b'Content-Length: '+str(len(body)).encode()+b'\r\nConnection: close\r\n\r\n'+body)
                client['close'] = True
            self._enqueue(client, 'hello', response)
        else:
            # SSE is server-to-client only, bounded HTTP request is already done.
            self._drop(client)

    def _broadcast(self, item):
        target, kind, payload, fields = item
        packet = self._packet(kind, payload, **fields)
        for client in list(self._clients.values()):
            if target is not None and target != client['id']:
                continue
            if client['kind'] == 'tcp':
                self._enqueue(client, kind, packet)
            elif client['kind'] == 'sse' and target is None and not payload:
                self._enqueue(client, kind, b'data: '+json.dumps(dict(fields, type=kind),
                              allow_nan=False, separators=(',', ':')).encode()+b'\n\n')
            elif client['kind'] == 'sse' and kind == 'spectrum':
                if time.monotonic()-client['sse_last'] < .2:
                    continue
                import struct
                values = struct.unpack('<1024h', payload)
                client['sse_last'] = time.monotonic()
                self._enqueue(client, kind, b'data: '+json.dumps(dict(fields, type=kind, values=values),
                              allow_nan=False, separators=(',', ':')).encode()+b'\n\n')

    def _run(self):
        listeners = []
        cpu = time.thread_time()
        try:
            self._selector = selectors.DefaultSelector()
            for port, kind in ((self.tcp_port, 'tcp'), (self.http_port, 'http')):
                listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                listeners.append(listener)
                option = getattr(socket, 'SO_EXCLUSIVEADDRUSE', socket.SO_REUSEADDR)
                listener.setsockopt(socket.SOL_SOCKET, option, 1)
                listener.bind((self.address, port))
                listener.listen(3)
                listener.setblocking(False)
                self._selector.register(listener, selectors.EVENT_READ, kind)
                if kind == 'tcp':
                    self.tcp_port = listener.getsockname()[1]
                else:
                    self.http_port = listener.getsockname()[1]
            self._ready.set()
            while not self._stop.is_set():
                for _ in range(64):
                    try:
                        item = self._out.get_nowait()
                    except queue.Empty:
                        break
                    self._broadcast(item)
                for key, mask in self._selector.select(.01):
                    client = key.data
                    if isinstance(client, str):
                        self._accept(key.fileobj, client)
                        continue
                    try:
                        if mask & selectors.EVENT_READ:
                            self._read(client)
                        if client['id'] not in self._clients:
                            continue
                        if mask & selectors.EVENT_WRITE:
                            packet = client['queue'].peek()
                            if packet:
                                count = client['socket'].send(packet)
                                if count:
                                    client['queue'].consume(count)
                            if not client['queue'].pending:
                                if client['close']:
                                    self._drop(client)
                                else:
                                    self._selector.modify(client['socket'], selectors.EVENT_READ, client)
                    except BlockingIOError:
                        pass
                    except (OSError, ValueError):
                        self._drop(client)
                for client in list(self._clients.values()):
                    if client['kind'] == 'http' and time.monotonic()-client['accepted'] > 5:
                        self._drop(client)
                self.stats['cpu_s'] = time.thread_time()-cpu
                self.stats['client_drops'] = self._closed_drops + sum(c['queue'].dropped for c in self._clients.values())
        except BaseException as error:
            self._error = error
            self._ready.set()
        finally:
            for client in list(self._clients.values()):
                self._drop(client)
            if self._selector:
                self._selector.close()
            for listener in listeners:
                listener.close()
