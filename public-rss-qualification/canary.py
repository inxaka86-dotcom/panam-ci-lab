"""Standalone public RSS qualification. No network on import or --self-test."""
import argparse
import hashlib
import ipaddress
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
from xml.parsers import expat

HOST = 'www.consultant.ru'
SOURCES = ('/rss/nw.xml', '/rss/fks.xml')
CAP = 65536
HEADER_CAP = 16384
OUTPUT_CAP = CAP + HEADER_CAP + 128
AGENT = 'Public-RSS-Qualification/1.0'


class Stop(ValueError):
    pass


def validated_address(answers):
    values = sorted({ipaddress.ip_address(x) for x in answers}, key=lambda x: (x.version, int(x)))
    if not values or any(not x.is_global or x.is_multicast or x.is_reserved for x in values):
        raise Stop('DNS_NOT_PUBLIC')
    return values[0]


def command(curl, index, address):
    if type(index) is not int or index not in (0, 1):
        raise Stop('INVALID_SOURCE')
    ip = validated_address([str(address)])
    pinned = f'[{ip}]' if ip.version == 6 else str(ip)
    return [curl, '-q', '--silent', '--globoff', '--noproxy', '*', '--proto', '=https',
            '--http1.1', '--tlsv1.2', '--retry', '0', '--max-redirs', '0',
            '--connect-timeout', '5', '--max-time', '8', '--max-filesize', str(CAP),
            '--include', '--header', 'Accept: application/rss+xml, application/xml, text/xml',
            '--header', 'Accept-Encoding: identity', '--user-agent', AGENT,
            '--resolve', f'{HOST}:443:{pinned}', '--write-out', '\n%{http_code}\n%{remote_ip}',
            'https://' + HOST + SOURCES[index]]


def parse_response(raw, address):
    if len(raw) > OUTPUT_CAP:
        raise Stop('OUTPUT_LIMIT')
    data, sep, peer = raw.rpartition(b'\n')
    response, sep2, code = data.rpartition(b'\n')
    if not sep or not sep2 or len(code) != 3 or not code.isdigit():
        raise Stop('RESPONSE_FORMAT')
    try:
        actual = ipaddress.ip_address(peer.decode('ascii'))
    except (ValueError, UnicodeError) as exc:
        raise Stop('PEER_INVALID') from exc
    if actual != address:
        raise Stop('PEER_MISMATCH')
    status = int(code)
    header, separator, body = response.partition(b'\r\n\r\n')
    if not separator or len(header) > HEADER_CAP or len(body) > CAP:
        raise Stop('RESPONSE_LIMIT')
    lines = header.split(b'\r\n')
    if not lines[0].startswith(b'HTTP/1.1 ' + code + b' ') and not lines[0].startswith(b'HTTP/1.0 ' + code + b' '):
        raise Stop('RESPONSE_FORMAT')
    if status in (401, 403): raise Stop('ACCESS_DENIED')
    if status == 429: raise Stop('RATE_LIMITED')
    if 300 <= status < 400: raise Stop('REDIRECT_STOP')
    if status != 200: raise Stop('HTTP_NOT_200')
    headers = {}
    for line in lines[1:]:
        name, colon, value = line.partition(b':')
        if not colon or not name or name.strip() != name:
            raise Stop('HEADER_FORMAT')
        key = name.lower()
        if key in (b'content-type', b'content-encoding', b'content-length', b'transfer-encoding'):
            if key in headers: raise Stop('DUPLICATE_HEADER')
            headers[key] = value.strip().lower()
    if headers.get(b'content-encoding', b'identity') != b'identity': raise Stop('ENCODING')
    if b'content-length' in headers:
        if b'transfer-encoding' in headers or not headers[b'content-length'].isdigit() or int(headers[b'content-length']) != len(body):
            raise Stop('LENGTH_MISMATCH')
    if headers.get(b'transfer-encoding', b'chunked') != b'chunked': raise Stop('TRANSFER_ENCODING')
    if headers.get(b'content-type', b'').split(b';', 1)[0].strip() not in (b'application/rss+xml', b'application/xml', b'text/xml'):
        raise Stop('CONTENT_TYPE')
    return body


def count_rss(raw):
    if len(raw) > CAP: raise Stop('BODY_LIMIT')
    try:
        text = raw.decode('utf-8-sig', errors='strict')
    except UnicodeError as exc:
        raise Stop('UTF8_REQUIRED') from exc
    if '\x00' in text: raise Stop('NUL')
    parser = expat.ParserCreate(encoding='UTF-8', namespace_separator='|')
    stack, count, nodes = [], 0, 0
    root = None
    def reject(*args): raise Stop('DTD_ENTITY')
    def decl(version, encoding, standalone):
        if encoding and encoding.lower() not in ('utf-8', 'utf8'): raise Stop('UTF8_REQUIRED')
    def start(name, attrs):
        nonlocal count, nodes, root
        nodes += 1
        stack.append(name)
        if root is None: root = name
        if len(stack) > 32 or nodes > 4096: raise Stop('XML_LIMIT')
        if stack == ['rss', 'channel', 'item']:
            count += 1
            if count > 128: raise Stop('ITEM_LIMIT')
    def end(name): stack.pop()
    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = reject
    parser.XmlDeclHandler = decl
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    try: parser.Parse(raw, True)
    except expat.ExpatError as exc: raise Stop('XML_INVALID') from exc
    if root != 'rss': raise Stop('NOT_RSS')
    return count


def one(index):
    # Parent timeout bounds DNS, process lifetime, and parsing. No retries.
    ips = [a[4][0] for a in socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)]
    ip = validated_address(ips)
    curl = shutil.which('curl', path='/usr/bin:/bin')
    if not curl: raise Stop('CURL_MISSING')
    with subprocess.Popen(command(curl, index, ip), env={'LC_ALL':'C'}, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
        raw = proc.stdout.read(OUTPUT_CAP+1)
        if len(raw)>OUTPUT_CAP:
            proc.kill(); proc.wait(); raise Stop('OUTPUT_LIMIT')
        rc = proc.wait(timeout=1)
    if rc: raise Stop({28:'TIMEOUT',60:'TLS_DENIED',63:'BODY_LIMIT'}.get(rc,'TRANSPORT_ERROR'))
    body = parse_response(raw, ip)
    return {'source_index':index,'status':'OK','http_status':200,'body_bytes':len(body),
            'content_sha256':hashlib.sha256(body).hexdigest(),'rss_items':count_rss(body),
            'peer_pinned':True,'tls_verified':True}


def selftest():
    ip=ipaddress.ip_address('8.8.8.8')
    assert validated_address(['8.8.8.8']) == ip
    assert command('/usr/bin/curl',0,ip)[-1] == 'https://'+HOST+SOURCES[0]
    assert command('/usr/bin/curl',1,ip)[-1] == 'https://'+HOST+SOURCES[1]
    assert '--location' not in command('/usr/bin/curl',0,ip)
    body=b'<rss><channel><item><title>sample</title></item></channel></rss>'
    def packet(code=200, data=body, headers=b'Content-Type: application/rss+xml\r\n', peer=b'8.8.8.8'):
        return b'HTTP/1.1 '+str(code).encode()+b' Test\r\n'+headers+b'\r\n'+data+b'\n'+str(code).encode()+b'\n'+peer
    assert parse_response(packet(),ip)==body and count_rss(body)==1
    negatives=[lambda:validated_address(['8.8.8.8','127.0.0.1']),lambda:validated_address(['224.0.0.1']),lambda:validated_address([]),lambda:command('/usr/bin/curl',2,ip),
               lambda:parse_response(packet(403),ip),lambda:parse_response(packet(429),ip),lambda:parse_response(packet(302),ip),lambda:parse_response(packet(peer=b'8.8.4.4'),ip),
               lambda:parse_response(packet(headers=b'Content-Type: text/html\r\n'),ip),lambda:parse_response(packet(headers=b'Content-Type: application/rss+xml\r\nContent-Encoding: gzip\r\n'),ip),
               lambda:parse_response(packet(data=b'x'*(CAP+1)),ip),lambda:parse_response(packet(headers=b'Content-Type: application/rss+xml\r\nContent-Length: 1\r\n'),ip),
               lambda:count_rss(b'<!DOCTYPE rss [<!ENTITY x "a">]><rss>&x;</rss>'),lambda:count_rss(b'<html/>'),lambda:count_rss(b'<rss>'),lambda:count_rss(b'\xff'),lambda:count_rss(b'<rss>'+b'<x>'*32+b'</x>'*32+b'</rss>')]
    for check in negatives:
        try: check()
        except Stop: pass
        else: raise AssertionError('negative accepted')
    print(json.dumps({'offline_assertions':5+len(negatives),'external_requests':0,'status':'PASS'}))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--self-test',action='store_true')
    group.add_argument('--live',action='store_true')
    group.add_argument('--one',type=int,choices=(0,1))
    p.add_argument('--policy-reviewed',action='store_true')
    a=p.parse_args()
    if a.self_test: selftest(); return
    if not a.policy_reviewed: p.error('external policy review required before network execution')
    if a.one is not None:
        try: result=one(a.one)
        except Stop as exc: result={'source_index':a.one,'status':str(exc)}
        except (OSError, subprocess.SubprocessError, ValueError): result={'source_index':a.one,'status':'LOCAL_FAILURE'}
        print(json.dumps(result)); return
    for i in range(len(SOURCES)):
        try:
            with subprocess.Popen([sys.executable,os.path.abspath(__file__),'--one',str(i),'--policy-reviewed'],env={'LC_ALL':'C'},stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True) as child:
                try:
                    output,_=child.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    try: os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                    child.communicate()
                    raise
                if child.returncode: raise Stop('WORKER_FAILURE')
            row=json.loads(output)
        except (OSError,subprocess.SubprocessError,ValueError): row={'source_index':i,'status':'WORKER_FAILURE_OR_DEADLINE'}
        print(json.dumps(row,sort_keys=True),flush=True)
        if row['status']!='OK': raise SystemExit(2)


if __name__=='__main__': main()
