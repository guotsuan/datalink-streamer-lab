#!/usr/bin/env python3
"""Sequential iperf3 reverse TCP -> DataLink/Product Streamer benchmark.
Python 3.9+, local iperf3 and SSH; remote iperf3 and Python 3 required.
Default: transfer 1 GB (1,000,000,000 bytes) and discard, with no total time limit.
--full --confirm-1tb opts into ~1 TB.
Only synthetic lab credentials: this endpoint uses HTTP, not TLS.
"""
import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import select
import subprocess
import sys
import time
import urllib.request as request
import urllib.parse as parse
import urllib.error
from http.cookiejar import CookieJar
import xml.etree.ElementTree as ET

class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args): return None

def source_sha256(size):
    """Hash the requested range from the actual source file over SSH, independently of HTTP."""
    if not shutil.which('ssh'): raise RuntimeError('SSH is required to prepare the source checksum')
    code = f'''import os,hashlib,json,stat
fd = os.open('/home/gq/datalink-streamer-lab/storage/lab.test/large-1tb.fits',os.O_RDONLY|os.O_NOFOLLOW)
with os.fdopen(fd,'rb') as f:
    before = os.fstat(f.fileno())
    if not stat.S_ISREG(before.st_mode) or before.st_size < {size}: raise RuntimeError('Invalid source file')
    remaining = {size}
    h = hashlib.sha256()
    while remaining:
        block = f.read(min(8*1024*1024,remaining))
        if not block: raise RuntimeError('Source file ended early')
        h.update(block)
        remaining -= len(block)
    after = os.fstat(f.fileno())
    if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns): raise RuntimeError('Source changed during hashing')
print(json.dumps({{'sha256':h.hexdigest(),'bytes':{size},'range':'bytes=0-{size-1}','method':'independent SSH read of source file'}}))
'''
    print(f'Preparing independent source SHA-256 for {size/1e9:g} GB...', flush=True)
    run = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','gq@64.176.188.89',
        'python3 -c '+shlex.quote(code)],capture_output=True,text=True)
    if run.returncode: raise RuntimeError('Source checksum preparation failed')
    reference = json.loads(run.stdout)
    if reference.get('bytes') != size: raise RuntimeError('Source checksum range mismatch')
    return reference

def iperf_baseline(seconds, port):
    """Direct reverse single-stream TCP; SSH controls lifecycle, not data transport."""
    if not shutil.which('iperf3') or not shutil.which('ssh'):
        raise RuntimeError('Install iperf3 and SSH locally; use --skip-iperf only for download-only tests')
    # One-off process and a source-restricted, expiring runtime firewall rule.
    remote = f'''import subprocess,sys,time,select,os,ipaddress,shutil
p = None
added = False
peer = ipaddress.ip_address(os.environ['SSH_CONNECTION'].split()[0])
if peer.version != 4: raise RuntimeError('IPv4 SSH connection required')
rule = 'rule family="ipv4" source address="'+str(peer)+'/32" port port="{port}" protocol="tcp" accept'
def fw(*args):
    return subprocess.run(['sudo','-n','firewall-cmd',*args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
try:
    if shutil.which('firewall-cmd'):
        if fw('--state').returncode != 0: raise RuntimeError('Unable to inspect firewalld')
        if fw('--query-rich-rule='+rule).returncode != 0:
            if fw('--add-rich-rule='+rule,'--timeout=60').returncode != 0: raise RuntimeError('Cannot create temporary firewall rule')
            added = True
    p = subprocess.Popen(['timeout','60','iperf3','-s','-1','-B','64.176.188.89','-p','{port}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    if p.poll() is not None: raise RuntimeError('iperf3 failed to start (missing binary or occupied port)')
    print('READY', flush=True)
    select.select([sys.stdin],[],[],50)
finally:
    if p is not None and p.poll() is None:
        p.terminate()
        try: p.wait(timeout=3)
        except subprocess.TimeoutExpired: p.kill(); p.wait()
    if added: fw('--remove-rich-rule='+rule)
'''
    server = subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',
        'gq@64.176.188.89','python3 -u -c '+shlex.quote(remote)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        ready, _, _ = select.select([server.stdout], [], [], 15)
        if not ready or server.stdout.readline().strip() != 'READY':
            raise RuntimeError('Temporary iperf server did not start; check SSH access and remote iperf3')
        print(f'iperf3: reverse TCP, one stream, {seconds}s; server -> this computer', flush=True)
        started = datetime.now(timezone.utc).isoformat()
        run = subprocess.run(['iperf3','-c','64.176.188.89','-p',str(port),'-R','-P','1',
            '-t',str(seconds),'--connect-timeout','5000','-J'], capture_output=True, text=True, timeout=seconds+15)
        try: raw = json.loads(run.stdout)
        except ValueError: raise RuntimeError('iperf3 did not return JSON') from None
        if run.returncode or raw.get('error'):
            raise RuntimeError('iperf3 failed: '+str(raw.get('error','connection or execution error')))
        measured = raw['end']['sum_received']
        bps = float(measured['bits_per_second'])
        if bps <= 0: raise RuntimeError('iperf3 returned no usable throughput')
        return {'started_at_utc':started, 'direction':'server-to-client', 'parallel_streams':1,
            'transport':'direct TCP (not SSH tunnel)', 'Mbit_s':round(bps/1e6,3),
            'MiB_s':round(bps/8/1048576,3), 'bytes':measured['bytes'],
            'seconds':measured['seconds'], 'raw':raw}
    finally:
        try: server.communicate(input='STOP\n', timeout=6)
        except subprocess.TimeoutExpired:
            server.kill(); server.communicate()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://64.176.188.89:18080')
    size_group = parser.add_mutually_exclusive_group()
    size_group.add_argument('--bytes', type=int, default=1000000000, help='Download bytes; default 1 GB (decimal)')
    size_group.add_argument('--mib', type=int, help='Optional sample size in MiB instead of decimal bytes')
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--confirm-1tb', action='store_true')
    parser.add_argument('--skip-iperf', action='store_true', help='Explicit download-only mode; no comparison')
    parser.add_argument('--iperf-seconds', type=int, default=10, help='Reverse TCP baseline duration, 1..30 seconds')
    parser.add_argument('--iperf-port', type=int, default=5201, help='Temporary TCP port; source-restricted 60s firewalld rule via sudo')
    parser.add_argument('--report', type=Path, help='Save measurements to a NEW JSON file')
    parser.add_argument('--output', type=Path, help='Optional NEW output file; partial samples are not complete FITS files')
    parser.add_argument('--expected-sha256', help='Trusted SHA-256 for the exact requested range; otherwise computed from source over SSH')
    args = parser.parse_args()
    if args.full and not args.confirm_1tb: parser.error('--full requires --confirm-1tb (real network charges may apply)')
    if args.mib is not None and not 1 <= args.mib <= 10240: parser.error('--mib must be 1..10240; use explicit --full for ~1 TB')
    if not 1 <= args.bytes <= 10*1024**3: parser.error('--bytes must be 1..10737418240; use explicit --full for ~1 TB')
    if not 1 <= args.iperf_seconds <= 30: parser.error('--iperf-seconds must be 1..30')
    if not 1024 <= args.iperf_port <= 65535: parser.error('--iperf-port must be 1024..65535')
    if args.report and (args.report.exists() or args.report.is_symlink()): parser.error('Report exists; refusing overwrite')
    if args.expected_sha256 and (len(args.expected_sha256)!=64 or any(c not in '0123456789abcdefABCDEF' for c in args.expected_sha256)):
        parser.error('--expected-sha256 must be 64 hexadecimal characters')
    base = args.base.rstrip('/')
    if base != 'http://64.176.188.89:18080': parser.error('This client is restricted to the laboratory origin')
    client = request.build_opener(request.ProxyHandler({}), NoRedirect(), request.HTTPCookieProcessor(CookieJar()))
    def open_url(path, data=None, headers=None):
        return client.open(request.Request(base+path, data=data, headers=headers or {}), timeout=10)
    password = getpass.getpass('Disposable laboratory password (HTTP; never use a real SKA password): ')
    try:
        open_url('/login', parse.urlencode({'password':password}).encode(), {'Origin':base})
    except urllib.error.HTTPError as e:
        if e.code != 303: raise RuntimeError(f'Login HTTP {e.code}') from None
        e.close()
    finally: del password
    with open_url('/lab/large/info') as r: info = json.load(r)
    requested = args.mib*1048576 if args.mib is not None else args.bytes
    expected = info['bytes'] if args.full else requested
    if expected > info['bytes']: raise RuntimeError('Requested sample exceeds the source file size')
    if args.output:
        if args.output.exists() or args.output.is_symlink(): parser.error('Output exists; refusing overwrite')
        if shutil.disk_usage(args.output.parent).free < expected + 1048576: parser.error('Not enough free space for output')
    with open_url('/datalink/v1/links?id='+parse.quote(info['did'])) as r: xml = r.read(1048576)
    root = ET.fromstring(xml)
    ns = {'v':'http://www.ivoa.net/xml/VOTable/v1.3'}
    p = root.find('.//v:RESOURCE[@ID="product-streamer"]/v:PARAM[@name="accessURL"]', ns)
    if p is None or p.get('value') != base+'/streamer/v1/data/product': raise RuntimeError('Unapproved or missing Streamer URL')
    headers = {'Origin':base, 'Content-Type':'application/xml', 'Authorization':'Bearer lab-service-token', 'Accept-Encoding':'identity'}
    if not args.full: headers['Range'] = f'bytes=0-{expected-1}'
    reference = {'sha256':args.expected_sha256.lower(),'bytes':expected,'method':'user-supplied reference'} if args.expected_sha256 else source_sha256(expected)
    baseline = None
    if not args.skip_iperf:
        try: baseline = iperf_baseline(args.iperf_seconds, args.iperf_port)
        except Exception as error:
            if args.report:
                with args.report.open('x') as f:
                    json.dump({'iperf':{'status':'failed','error':str(error)},'download':{'status':'not_started'}}, f, indent=2)
            raise
        print(f'iperf3 receive: {baseline["Mbit_s"]:.2f} Mbit/s; now starting Streamer download', flush=True)
    sink = None
    received = 0
    first_byte = None
    stop_reason = 'error'
    prefix = bytearray()
    zero_data_ok = True
    hasher = hashlib.sha256()
    checksum_matches = False
    started_at = datetime.now(timezone.utc).isoformat()
    start = time.monotonic(); last = start
    try:
        with open_url('/streamer/v1/data/product', xml, headers) as r:
            if r.status != (200 if args.full else 206): raise RuntimeError(f'Unexpected HTTP {r.status}')
            if int(r.headers.get('Content-Length','-1')) != expected: raise RuntimeError('Unexpected length')
            if not args.full and r.headers.get('Content-Range') != f'bytes 0-{expected-1}/{info["bytes"]}': raise RuntimeError('Unexpected range')
            if r.headers.get('Content-Encoding','identity') != 'identity': raise RuntimeError('Compressed transfer rejected')
            if args.output: sink = args.output.open('xb')
            while True:
                block = r.read1(1024*1024)
                if not block: break
                hasher.update(block)
                if first_byte is None: first_byte = time.monotonic()-start
                header_bytes = min(len(block), max(0, 2880-received))
                if header_bytes: prefix.extend(block[:header_bytes])
                zero_data_ok = zero_data_ok and block[header_bytes:].count(0) == len(block)-header_bytes
                received += len(block)
                if received > expected: raise RuntimeError('Too many bytes')
                if sink: sink.write(block)
                now = time.monotonic()
                if now-last >= 2:
                    print(f'\r{received/1e9:.3f} GB / {expected/1e9:.3f} GB; average {received/(now-start)/1048576:.2f} MiB/s', end='', flush=True)
                    last = now
            if received != expected: raise RuntimeError('Incomplete transfer')
            if not zero_data_ok: raise RuntimeError('Nonzero bytes in synthetic zero-filled data')
            if len(prefix) == 2880 and not (prefix.startswith(b'SIMPLE  =                    T') and any(prefix[i:i+80].rstrip() == b'END' for i in range(0,2880,80))):
                raise RuntimeError('Unexpected FITS header')
            checksum_matches = hasher.hexdigest() == reference['sha256']
            if not checksum_matches: raise RuntimeError('SHA-256 mismatch against source reference')
            if received == expected: stop_reason = 'complete'
    finally:
        if sink: sink.close()
        elapsed = time.monotonic()-start
        result = {'started_at_utc':started_at, 'base_url':base, 'did':info['did'],
              'bytes':received, 'expected':expected, 'complete':stop_reason=='complete', 'stop_reason':stop_reason,
              'full_1tb_test':args.full, 'seconds':round(elapsed,3), 'average_MiB_s':round(received/max(elapsed,.001)/1048576,3),
              'average_Mbit_s':round(received*8/max(elapsed,.001)/1e6,3),
              'first_byte_seconds':round(first_byte,3) if first_byte is not None else None,
              'sample_header_and_zero_data_check':bool(len(prefix)==2880 and prefix.startswith(b'SIMPLE  =                    T') and any(prefix[i:i+80].rstrip() == b'END' for i in range(0,2880,80)) and zero_data_ok),
              'sink':str(args.output) if args.output else 'discard', 'sha256':hasher.hexdigest(),
              'sha256_reference':reference, 'sha256_matches':checksum_matches}
        result['iperf'] = baseline or {'status':'skipped'}
        result['download_to_iperf_percent'] = round(result['average_Mbit_s']/baseline['Mbit_s']*100,2) if baseline and stop_reason == 'complete' and received else None
        result['comparison_note'] = 'Sequential single-stream sample, not a maximum-capacity or full-1-TB certification; HTTP includes request setup and content checks. Different ports may encounter different network policy.'
        console = dict(result)
        console['iperf'] = {k:v for k,v in result['iperf'].items() if k != 'raw'}
        print('\n'+json.dumps(console))
        if args.report:
            with args.report.open('x') as f: json.dump(result, f, indent=2)

if __name__ == '__main__':
    try: main()
    except KeyboardInterrupt: sys.exit('Stopped by user; any output file is incomplete.')
    except Exception as e: sys.exit(f'{type(e).__name__}: {e}')
