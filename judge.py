"""Private Judge0 adapter. Student code never executes inside the API process.
Enable only against a self-hosted, network-isolated Judge0 installation.
"""
import base64
import os
import time
from urllib.parse import urlparse
import requests
from fastapi import HTTPException


def configured():
    url=os.getenv('JUDGE0_URL','').strip()
    parts=urlparse(url)
    return bool(parts.scheme=='https' and parts.hostname and not parts.username and not parts.password and os.getenv('JUDGE0_ENABLED')=='true')


def run_cases(code,language,tests):
    if not configured(): raise HTTPException(503,'Judge unavailable')
    languages={'Python':int(os.getenv('JUDGE0_PYTHON_ID','71')),'JavaScript':int(os.getenv('JUDGE0_JAVASCRIPT_ID','63'))}
    if language not in languages: raise HTTPException(422,'Unsupported execution language')
    base=os.environ['JUDGE0_URL'].rstrip('/')
    headers={'Content-Type':'application/json'}
    if os.getenv('JUDGE0_AUTH_TOKEN'): headers['X-Auth-Token']=os.environ['JUDGE0_AUTH_TOKEN']
    def enc(s): return base64.b64encode(s.encode()).decode()
    def dec(s): return base64.b64decode(s or '',validate=True).decode('utf-8',errors='replace')[:10000]
    if language=='JavaScript':
        code="globalThis.prompt = (() => { const lines = require('fs').readFileSync(0,'utf8').replace(/\\r/g,'').split('\\n'); let i=0; return () => i<lines.length ? lines[i++] : null; })();\n"+code
    submissions=[dict(language_id=languages[language],source_code=enc(code),stdin=enc(t['stdin']),
        cpu_time_limit=2,wall_time_limit=5,memory_limit=128000,max_processes_and_or_threads=16,
        max_file_size=64,enable_network=False,number_of_runs=1) for t in tests]
    deadline=time.monotonic()+40
    try:
        with requests.Session() as session:
            session.trust_env=False
            response=session.post(base+'/submissions/batch?base64_encoded=true',headers=headers,json={'submissions':submissions},timeout=8,allow_redirects=False)
            response.raise_for_status(); tokens=[x['token'] for x in response.json()]
            if len(tokens)!=len(tests): raise ValueError('Invalid batch')
            while time.monotonic()<deadline:
                response=session.get(base+'/submissions/batch',headers=headers,params={'tokens':','.join(tokens),'base64_encoded':'true','fields':'stdout,stderr,compile_output,status'},timeout=8,allow_redirects=False)
                response.raise_for_status(); values=response.json()['submissions']
                if len(values)!=len(tests): raise ValueError('Invalid batch')
                if all(x and x['status']['id']>2 for x in values):
                    result=[]
                    for actual,test in zip(values,tests):
                        status=actual['status']['id']; stdout=dec(actual.get('stdout'))
                        error=None if status==3 else ('Time limit exceeded' if status==5 else dec(actual.get('compile_output')) or dec(actual.get('stderr')) or actual['status']['description'])
                        if status>=13: raise ValueError('Judge internal error')
                        result.append({'stdout':stdout,'error':error,'passed':status==3 and stdout.strip()==test['expected_stdout'].strip()})
                    return result
                time.sleep(.5)
    except (requests.RequestException,ValueError,KeyError,TypeError):
        raise HTTPException(503,'Judge unavailable') from None
    raise HTTPException(503,'Judge timeout')


def public_results(results):
    # Hidden input/output must never be returned, including echoed input in errors.
    return [{'passed':r['passed'],'stdout':'','error':None if r['passed'] else 'Test failed'} for r in results]
