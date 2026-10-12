"""Non-secret profiles and user-scoped, encrypted Windows credentials."""
from dataclasses import dataclass, field, asdict
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import uuid

from ..media import atomic_json


PRESETS = {
    'openrouter': ('OpenRouter', 'https://openrouter.ai/api/v1', ('story', 'script', 'image', 'voice', 'video'), {}),
    'ollama': ('Ollama', 'http://127.0.0.1:11434', ('story', 'script'), {}),
    'openai_compatible': ('OpenAI-compatible / open model server', 'https://api.openai.com/v1', ('story', 'script', 'image', 'voice'), {}),
    'elevenlabs': ('ElevenLabs', 'https://api.elevenlabs.io/v1', ('voice',), {'voice_id': ''}),
    'comfyui': ('ComfyUI', 'http://127.0.0.1:8188', ('image', 'video'), {'workflow': {}}),
    'runway': ('Runway', 'https://api.dev.runwayml.com/v1', ('video',), {'duration': 5, 'ratio': '720:1280'}),
    'http': ('JSON HTTP API', 'http://127.0.0.1:8000', (), {}),
    'mcp_stdio': ('MCP local program', '', (), {'command': '', 'args': []}),
    'mcp_http': ('MCP Streamable HTTP', 'http://127.0.0.1:8000/mcp', (), {}),
}
MODES = ('disabled', 'local', 'online')


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value):
        raise ValueError('Invalid connection/job identifier')
    return value


@dataclass
class Connection:
    id: str
    name: str
    provider: str
    base_url: str
    model: str = ''
    enabled: bool = False
    key_env: str = ''
    options: dict = field(default_factory=dict)

    def validate(self):
        identifier(self.id)
        if not isinstance(self.provider, str) or self.provider not in PRESETS:
            raise ValueError('Unsupported connection provider')
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError('Connection needs a name')
        if any(not isinstance(v, str) for v in (self.base_url, self.model, self.key_env)):
            raise ValueError('Connection URL, model and environment name must be text')
        if type(self.enabled) is not bool or not isinstance(self.options, dict):
            raise ValueError('Invalid connection settings')
        # Credentials only belong in the encrypted vault or an environment variable.
        forbidden = {'api_key', 'apikey', 'authorization', 'xi-api-key', 'token', 'password', 'headers', 'env'}
        def check(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if str(key).lower() in forbidden:
                        raise ValueError(f'Use the secure credential field, not options.{key}')
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)
        check(self.options)
        from urllib.parse import urlsplit
        if urlsplit(self.base_url).query:
            raise ValueError('Base URLs cannot contain query parameters; use the secure credential field for keys')
        if self.key_env and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', self.key_env):
            raise ValueError('Invalid credential environment variable name')
        return self

    @classmethod
    def preset(cls, provider):
        name, url, _, options = PRESETS[provider]
        return cls(uuid.uuid4().hex, name, provider, url, options=json.loads(json.dumps(options)))


class ConnectionStore:
    def __init__(self, root: Path):
        self.path = Path(root) / '.studio_connections.json'

    def load(self):
        if not self.path.exists():
            return 'disabled', []
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('version') != 1 or data.get('mode') not in MODES:
            raise ValueError('Unsupported connections configuration')
        if not isinstance(data.get('connections'), list):
            raise ValueError('Connections configuration needs a connections array')
        try:
            records = [Connection(**record).validate() for record in data['connections']]
        except TypeError:
            raise ValueError('Each connection must be an object with valid profile fields') from None
        if len({c.id for c in records}) != len(records):
            raise ValueError('Duplicate connection ID')
        return data['mode'], records

    def save(self, mode, connections):
        if mode not in MODES:
            raise ValueError('Invalid connections mode')
        records = [asdict(c.validate()) for c in connections]
        if len({c['id'] for c in records}) != len(records):
            raise ValueError('Duplicate connection ID')
        atomic_json(self.path, {'version': 1, 'mode': mode, 'connections': records})


class _Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


def _protect(data: bytes, decrypt=False):
    if os.name != 'nt':
        raise ValueError('Secure key storage is Windows-only; use a credential environment variable on this OS.')
    buffer = ctypes.create_string_buffer(data)
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = _Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    method = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    method.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    method.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not method(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise OSError(ctypes.get_last_error(), 'Windows credential encryption failed')
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel.LocalFree(target.pbData)


class SecretStore:
    def __init__(self, root=None):
        self.root = Path(root) if root else Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'VideoNovelStudio' / 'credentials'

    def _path(self, key):
        return self.root / (identifier(key) + '.dpapi')

    def put(self, key, secret):
        if not secret.strip() or '\n' in secret or '\r' in secret:
            raise ValueError('Credential must be a nonempty single line')
        encrypted = _protect(secret.encode('utf-8'))
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        temporary = path.with_suffix('.tmp')
        try:
            temporary.write_bytes(encrypted)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def get(self, connection):
        if connection.key_env:
            result = os.environ.get(connection.key_env, '')
        else:
            path = self._path(connection.id)
            result = _protect(path.read_bytes(), True).decode('utf-8') if path.exists() else ''
        if '\n' in result or '\r' in result:
            raise ValueError('Credential contains a newline')
        return result

    def exists(self, connection):
        return bool(os.environ.get(connection.key_env)) if connection.key_env else self._path(connection.id).exists()

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)
