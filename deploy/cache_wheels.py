"""Warm an isolated cache from PyPI JSON metadata, verifying every wheel hash."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request
import urllib.parse
import time

CACHE=Path('/opt/jimeet-staging/wheels')
CACHE.mkdir(exist_ok=True)
PACKAGES={'Django':'6.1.2','psycopg':'3.3.6','psycopg-binary':'3.3.6',
          'djangorestframework':'3.18.3','gunicorn':'23.0.0','asgiref':'3.13.0',
          'sqlparse':'0.6.1','typing-extensions':'4.16.0','packaging':'26.3'}

def fetch(item):
    name,version=item
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=20) as r:
                metadata=json.load(r)
            break
        except Exception:
            if attempt==2: raise
            time.sleep(2)
    wheels=[f for f in metadata['urls'] if f['filename'].endswith('.whl')]
    compatible=[f for f in wheels if f['filename'].endswith('none-any.whl') or
                ('cp312-cp312-manylinux2014_x86_64' in f['filename'])]
    if len(compatible)!=1: raise RuntimeError(f'Unexpected wheel selection for {name}')
    item=compatible[0]
    target=CACHE/item['filename']
    expected=item['digests']['sha256']
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==expected:
        print('Verified cached '+target.name,flush=True)
        return
    package_path=urllib.parse.urlsplit(item['url']).path
    candidates=['https://mirrors.aliyun.com/pypi'+package_path,
                'https://pypi.tuna.tsinghua.edu.cn'+package_path,item['url']]
    for url in candidates:
        try:
            start=time.monotonic()
            part=target.with_suffix('.part')
            with urllib.request.urlopen(url,timeout=20) as response, part.open('wb') as output:
                while True:
                    chunk=response.read(64*1024)
                    if not chunk: break
                    output.write(chunk)
                    if time.monotonic()-start>90: raise TimeoutError('Slow package download')
            if hashlib.sha256(part.read_bytes()).hexdigest()!=expected:
                raise RuntimeError('Checksum mismatch')
            part.replace(target)
            break
        except Exception as exc:
            print(f'Retrying {name}: {type(exc).__name__}',flush=True)
    else:
        raise RuntimeError(f'Unable to obtain verified wheel for {name}')
    print('Verified '+target.name,flush=True)

with ThreadPoolExecutor(max_workers=4) as executor:
    list(executor.map(fetch,PACKAGES.items()))
