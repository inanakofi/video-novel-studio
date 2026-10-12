"""Explicit network boundary; no retries of potentially billable requests."""
import ipaddress
import json
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

from ..media import RenderCancelled


class ConnectionError(RuntimeError):
    pass


def check_cancel(cancel):
    if cancel and cancel.is_set():
        raise RenderCancelled('Stopped waiting. A submitted provider job may continue; use Resume to retrieve it.')


def validate_url(url, mode):
    if mode == 'disabled':
        raise ConnectionError('Connections are disabled. Offline editing and rendering remain available.')
    if mode not in ('local', 'online'):
        raise ConnectionError('Unknown connections mode')
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ConnectionError('Use an HTTP(S) URL without credentials or a fragment')
    host = parsed.hostname.lower()
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host == 'localhost'
    if mode == 'local' and not local:
        raise ConnectionError('Local-only mode permits localhost and loopback addresses only')
    if parsed.scheme != 'https' and not local:
        raise ConnectionError('Remote connections require HTTPS')
    # Prevent a modified hosts file from directing localhost credentials off-device.
    if host == 'localhost' and any(not ipaddress.ip_address(item[4][0]).is_loopback
                                  for item in socket.getaddrinfo(host, parsed.port or 80, type=socket.SOCK_STREAM)):
        raise ConnectionError('localhost does not resolve exclusively to loopback')
    return parsed


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Transport:
    def __init__(self, connection, mode, secret='', cancel=None, timeout=120):
        if not connection.enabled:
            raise ConnectionError('Enable this connection before using it')
        self.connection, self.mode, self.secret, self.cancel = connection, mode, secret, cancel
        self.timeout = timeout
        validate_url(connection.base_url, mode)

    def headers(self):
        headers = {'Accept': 'application/json', 'User-Agent': 'VideoNovelStudio/1.2'}
        if self.secret:
            if self.connection.provider == 'elevenlabs':
                headers['xi-api-key'] = self.secret
            else:
                headers['Authorization'] = 'Bearer ' + self.secret
        if self.connection.provider == 'runway':
            headers['X-Runway-Version'] = '2024-11-06'
        if self.connection.provider == 'openrouter':
            headers['X-Title'] = 'Video Novel Studio'
        return headers

    def url(self, path):
        if not isinstance(path, str) or not path.startswith('/') or path.startswith('//') or '\\' in path:
            raise ConnectionError('API path must start with a single /')
        return self.connection.base_url.rstrip('/') + path

    def _open(self, method, url, body, authenticated):
        check_cancel(self.cancel)
        parsed = validate_url(url, self.mode)
        base = urlsplit(self.connection.base_url)
        if authenticated and (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
            raise ConnectionError('Credentials cannot be sent to another origin')
        headers = self.headers() if authenticated else {'User-Agent': 'VideoNovelStudio/1.2'}
        data = None if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if data is not None:
            headers['Content-Type'] = 'application/json'
        # Do not inherit a proxy that could route loopback service traffic away.
        opener = build_opener(_NoRedirect(), ProxyHandler({}) if self.mode == 'local' or parsed.hostname in ('localhost', '127.0.0.1', '::1') else ProxyHandler())
        try:
            return opener.open(Request(url, data=data, headers=headers, method=method), timeout=self.timeout)
        except HTTPError as error:
            detail = ''
            try:
                payload = json.loads(error.read(4096))
                problem = payload.get('error', {}) if isinstance(payload, dict) else {}
                if isinstance(problem, dict) and isinstance(problem.get('message'), str):
                    detail = ' ' + problem['message'][:500].replace('\n', ' ').replace('\r', ' ')
                    if self.secret:
                        detail = detail.replace(self.secret, '[redacted]')
            except (ValueError, OSError):
                pass
            error.close()
            raise ConnectionError(f'{self.connection.name}: HTTP {error.code}.{detail} Check the endpoint, model, credentials and provider account. No automatic retry was made.') from None
        except (URLError, OSError, TimeoutError):
            raise ConnectionError(f'{self.connection.name}: connection failed or timed out. Submission outcome may be unknown; check provider history before submitting again.') from None

    def request(self, method, path, body=None, *, raw=False, capture_submission=False, limit=None):
        if method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE'):
            raise ConnectionError('Unsupported HTTP method')
        with self._open(method, self.url(path), body, True) as response:
            chunks, total = [], 0
            limit = limit if limit is not None else (64 * 1024**2 if raw else 16 * 1024**2)
            while True:
                # A queued job's tiny response contains its only recovery ID. Once
                # submitted, capture that response before honoring cancellation.
                if not capture_submission:
                    check_cancel(self.cancel)
                block = response.read(65536)
                if not block:
                    break
                total += len(block)
                if total > limit:
                    raise ConnectionError('Provider response exceeded the size limit')
                chunks.append(block)
        payload = b''.join(chunks)
        if raw:
            return payload
        try:
            result = json.loads(payload)
        except (ValueError, UnicodeError):
            raise ConnectionError('Provider returned invalid JSON') from None
        if not isinstance(result, (dict, list)):
            raise ConnectionError('Provider returned an unexpected response')
        return result

    def download(self, url, destination, *, authenticated=False):
        """Bounded streaming download. Redirects are deliberately rejected."""
        temporary = destination.with_suffix(destination.suffix + '.part')
        try:
            with self._open('GET', url, None, authenticated) as response, temporary.open('wb') as handle:
                total = 0
                deadline = time.monotonic() + 600
                while True:
                    check_cancel(self.cancel)
                    if time.monotonic() > deadline:
                        raise ConnectionError('Download exceeded ten minutes')
                    block = response.read(65536)
                    if not block:
                        break
                    total += len(block)
                    if total > 512 * 1024**2:
                        raise ConnectionError('Download exceeded 512 MiB')
                    handle.write(block)
            if not total:
                raise ConnectionError('Provider returned an empty file')
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
