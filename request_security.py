"""Whole-API request limits. Keep one worker; share an edge limiter before scaling."""
import os
from starlette.responses import JSONResponse
from performance import RateLimiter


class RequestSecurity:
    def __init__(self, app, general=None, auth=None):
        self.app = app
        self.general = general or RateLimiter(int(os.getenv('API_REQUESTS_PER_MINUTE', '120')), 3000)
        self.auth = auth or RateLimiter(int(os.getenv('AUTH_REQUESTS_PER_MINUTE', '15')), 100)
        self.max_body = 65536

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] == 'OPTIONS':
            return await self.app(scope, receive, send)
        identity = (scope.get('client') or ('unknown',))[0]
        # Never trust caller-supplied X-Forwarded-For. Configure trusted proxies in Uvicorn.
        for limiter in [self.general] + ([self.auth] if scope['path'].startswith('/auth/') else []):
            allowed, info = limiter.is_allowed(identity)
            if not allowed:
                return await JSONResponse({'detail': 'Too many requests. Try again later.'}, 429,
                    headers={'Retry-After': str(info['retry_after'])})(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > self.max_body:
                return await JSONResponse({'detail': 'Request body is too large'}, 413)(scope, receive, send)
            if not message.get('more_body', False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()

        await self.app(scope, replay, send)
