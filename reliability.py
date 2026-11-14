"""Safe structured server error records: no payloads, query strings, tokens or exception text."""
import json
import logging
import time
import uuid
from starlette.responses import JSONResponse

logger=logging.getLogger('mentor.reliability')

class ErrorMonitoring:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        request_id=uuid.uuid4().hex
        start=time.monotonic();status=500;started=False;failure=None
        async def wrapped(message):
            nonlocal status,started
            if message['type']=='http.response.start':
                started=True;status=message['status']
                message['headers']=list(message.get('headers',[]))+[(b'x-request-id',request_id.encode())]
            await send(message)
        try:
            await self.app(scope,receive,wrapped)
        except Exception as exc:
            failure=type(exc).__name__;status=500
            if not started:
                await JSONResponse({'detail':'Internal server error','request_id':request_id},500)(scope,receive,wrapped)
            else:
                raise
        finally:
            if status>=500:
                route=getattr(scope.get('route'),'path','unmatched')
                logger.error(json.dumps({'event':'server_error','request_id':request_id,'route':route,
                    'status':status,'exception_type':failure,'duration_ms':round((time.monotonic()-start)*1000)}))
