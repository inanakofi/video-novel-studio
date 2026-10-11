"""Explicit calls to user-configured software APIs and MCP servers."""
import asyncio
from contextlib import AsyncExitStack
import json
import os
from urllib.parse import urlsplit

from .generation import GenerationService
from .transport import ConnectionError, validate_url, check_cancel


def call_http(service: GenerationService, connection_id, method, path, body=None, cancel=None):
    transport = service.transport(connection_id, cancel)
    if transport.connection.provider != 'http':
        raise ValueError('Select a JSON HTTP API connection')
    if body is not None and not isinstance(body, (dict, list)):
        raise ValueError('HTTP request body must be a JSON object or array')
    return transport.request(method, path, body)


def mcp_action(service: GenerationService, connection_id, *, tool_name=None, arguments=None, cancel=None):
    """No automatic tool calls, sampling, OAuth browser flows or elicitation."""
    mode, connection = service.connection(connection_id)
    check_cancel(cancel)
    if connection.provider not in ('mcp_stdio', 'mcp_http'):
        raise ValueError('Select an MCP connection')
    try:
        from mcp import Client
        from mcp.client.stdio import StdioServerParameters, stdio_client
        from mcp.client.streamable_http import streamable_http_client
        import httpx2
    except ImportError:
        raise ConnectionError('MCP is optional. Install it with: python -m pip install -r requirements-integrations.txt') from None
    if arguments is not None and not isinstance(arguments, dict):
        raise ValueError('MCP tool arguments must be a JSON object')
    secret = service.secrets.get(connection)

    async def perform():
        async with AsyncExitStack() as stack:
            if connection.provider == 'mcp_stdio':
                command, args = connection.options.get('command'), connection.options.get('args', [])
                if not isinstance(command, str) or not command.strip() or not isinstance(args, list) or any(not isinstance(a, str) for a in args):
                    raise ValueError('MCP options need command (executable) and args (string array)')
                env = {}
                key_name = connection.options.get('credential_env', '')
                if secret:
                    import re
                    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key_name):
                        raise ValueError('Set options.credential_env to the variable expected by the MCP program')
                    env[key_name] = secret
                # SDK launches directly, hides the Windows console and kills its process tree on close.
                # Drop stderr instead of leaking arbitrary third-party environment/credential logs.
                errlog = stack.enter_context(open(os.devnull, 'w'))
                params = StdioServerParameters(command=command, args=args, env=env,
                                               cwd=connection.options.get('cwd') or str(service.root))
                transport = stdio_client(params, errlog=errlog)
            else:
                base = validate_url(connection.base_url, mode)
                async def check_request(request):
                    destination = validate_url(str(request.url), mode)
                    if (destination.scheme, destination.netloc) != (base.scheme, base.netloc):
                        raise ConnectionError('MCP requests cannot leave the configured origin')
                    check_cancel(cancel)
                client = await stack.enter_async_context(httpx2.AsyncClient(
                    headers={'Authorization': 'Bearer ' + secret} if secret else {}, timeout=60,
                    follow_redirects=False, trust_env=False, event_hooks={'request': [check_request]}))
                transport = streamable_http_client(connection.base_url, http_client=client)
            client = await stack.enter_async_context(Client(transport, read_timeout_seconds=120))
            if tool_name is None:
                tools, cursor = [], None
                for _ in range(50):
                    result = await client.list_tools(cursor=cursor)
                    data = result.model_dump(mode='json', by_alias=True)
                    tools.extend(data.get('tools', []))
                    cursor = data.get('nextCursor')
                    if not cursor:
                        break
                else:
                    raise ConnectionError('MCP tool listing exceeded 50 pages')
                return {'tools': tools}
            result = await client.call_tool(tool_name, arguments or {})
            data = result.model_dump(mode='json', by_alias=True)
            if data.get('isError'):
                raise ConnectionError('MCP tool reported a failure: ' + json.dumps(data.get('content', []), ensure_ascii=False)[:4000])
            return data

    async def guarded():
        # Keep cancellation inside the same asyncio task as SDK context managers.
        task = asyncio.create_task(perform())
        try:
            for _ in range(2400):
                if task.done():
                    return await task
                check_cancel(cancel)
                await asyncio.sleep(.1)
            raise ConnectionError('MCP call exceeded four minutes; the external tool may still have side effects')
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
    try:
        return asyncio.run(guarded())
    except Exception as error:
        def reasons(exception):
            children = getattr(exception, 'exceptions', None)
            if children:
                return '; '.join(reasons(child) for child in children)
            return str(exception) or type(exception).__name__
        message = reasons(error)
        if secret:
            message = message.replace(secret, '[redacted]')
        raise ConnectionError(message) from None
