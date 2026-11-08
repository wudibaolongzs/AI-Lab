"""Bounded official OpenAPI transport. No automatic retries or logging."""
import base64
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class Client:
    def _request(self, path, payload=None):
        token = os.environ.get('LUOGU_OPENAPP_TOKEN', '')
        if not token or ':' not in token:
            raise ValueError('OpenApp credentials unavailable')
        headers = {'Authorization': 'Basic ' + base64.b64encode(token.encode()).decode(),
                   'Content-Type': 'application/json'}
        request = Request('https://open-v1.lgapi.cn' + path,
                          data=json.dumps(payload).encode() if payload is not None else None,
                          headers=headers)
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            if response.status == 204:
                return None
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError('Response exceeds size limit')
            return json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))

    def submit(self, pid, language, code, track_id):
        return self._request('/judge/problem', {'pid': pid, 'lang': language,
                             'o2': True, 'code': code, 'trackId': track_id})

    def result(self, request_id):
        # Official OAS has an inconsistent path parameter declaration. Live mode
        # remains gated until an operator verifies the query form against Luogu.
        return self._request('/judge/result?' + urlencode({'id': request_id}))
