"""Bounded, non-interactive atomic writes over the Hrana HTTP protocol."""
import json
import os
from urllib.request import Request, urlopen

from backend.acquisition.publication import StalePublicationHeadError


def execute_atomic_batch(statements, *, timeout=30):
    def argument(value):
        if value is None:return {'type':'null'}
        if isinstance(value,int):return {'type':'integer','value':str(int(value))}
        if isinstance(value,float):return {'type':'float','value':value}
        return {'type':'text','value':str(value)}
    def step(sql,parameters=(),condition=None):
        result={'stmt':{'sql':sql,'args':[argument(v) for v in parameters],'want_rows':False}}
        if condition is not None:result['condition']=condition
        return result
    steps=[step('BEGIN IMMEDIATE')]
    for sql,parameters in statements:
        steps.append(step(sql,parameters,{'type':'ok','step':len(steps)-1}))
    commit_index=len(steps)
    steps.append(step('COMMIT',condition={'type':'ok','step':commit_index-1}))
    steps.append(step('ROLLBACK',condition={'type':'not','cond':{'type':'ok','step':commit_index}}))
    body={'requests':[{'type':'batch','batch':{'steps':steps}},{'type':'close'}]}
    url=os.environ['TURSO_DATABASE_URL'].replace('libsql://','https://').rstrip('/')+'/v2/pipeline'
    request=Request(url,data=json.dumps(body).encode(),headers={
        'Authorization':'Bearer '+os.environ['TURSO_AUTH_TOKEN'],'Content-Type':'application/json'})
    with urlopen(request,timeout=timeout) as response:payload=json.load(response)
    batch=payload['results'][0]
    if batch['type']!='ok':
        raise RuntimeError('Atomic publication batch failed: '+batch.get('error',{}).get('code','unknown'))
    result=batch['response']['result']
    errors=result['step_errors']
    # The first user statement is the optimistic guard. It deliberately fails
    # a NOT NULL constraint when the prepared head/revisions are stale.
    if len(errors)>1 and errors[1] is not None:
        if 'CONSTRAINT' in errors[1].get('code',''):
            raise StalePublicationHeadError('Publication inputs changed before the atomic HTTP batch.')
    if result['step_results'][commit_index] is None:
        error=next((e for e in errors[:commit_index+1] if e),{})
        raise RuntimeError('Atomic publication batch rolled back: '+error.get('code','unknown'))
