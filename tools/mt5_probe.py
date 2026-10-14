"""Signed SHADOW/status probe; reads only bridge credential, never MT5 credentials."""
import argparse,hashlib,hmac,json,secrets,time
from pathlib import Path
import requests
p=argparse.ArgumentParser();p.add_argument('action',choices=['status','shadow']);p.add_argument('--url',default='https://fx101-mt5-shadow.onrender.com');p.add_argument('--out');p.add_argument('--resolve',help='Temporary verified address for this test hostname only');a=p.parse_args()
if not a.url.startswith('https://'): raise SystemExit('HTTPS required')
if a.resolve:
    import socket, urllib.parse, ipaddress
    ipaddress.ip_address(a.resolve)
    hostname=urllib.parse.urlparse(a.url).hostname
    original=socket.getaddrinfo
    socket.getaddrinfo=lambda host,*args,**kwargs: original(a.resolve if host==hostname else host,*args,**kwargs)
key=Path('bridge-private/token.txt').read_text().strip().encode()
method,path=('GET','/fx101/mt5/status') if a.action=='status' else ('POST','/fx101/mt5/shadow-test')
body=b'';stamp=str(int(time.time()));nonce=secrets.token_hex(32)
signature=hmac.new(key,f'{method}\n{path}\n{stamp}\n{nonce}\n'.encode()+body,hashlib.sha256).hexdigest()
r=requests.request(method,a.url+path,data=body,headers={'X-FX101-Time':stamp,'X-FX101-Nonce':nonce,'X-FX101-Signature':signature},timeout=20)
result={'http_status':r.status_code,'response':r.json()}
if a.out: Path(a.out).write_text(json.dumps(result,indent=2))
if a.action=='status':
 s=result['response'].get('snapshot');print(json.dumps({'http_status':r.status_code,'connected':result['response'].get('connected'),
     'snapshot':None if not s else {k:s['payload'][k] for k in ['login','server','balance','equity','captured_at','positions','orders']}}))
else: print(json.dumps(result))
