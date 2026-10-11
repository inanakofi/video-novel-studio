import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import socket
import time
import tempfile
import unittest

from src.connections.config import Connection, ConnectionStore
from src.connections.generation import GenerationService
from src.connections.tools import call_http, mcp_action
from src.studio_mcp import StudioTools
from src.story_manager import StoryLibrary
from test_connections import ProviderFixture, DRAFT


class SoftwareConnectionTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('mcp'), 'Optional MCP dependency not installed')
    def test_actual_streamable_http_mcp_and_tool_failure(self):
        with tempfile.TemporaryDirectory(prefix='VNS HTTP MCP ') as folder:
            root = Path(folder)
            library = StoryLibrary(root)
            library.create_story('HTTP MCP series')
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            code = ('import sys; from src.studio_mcp import make_server; '
                    'make_server(sys.argv[1]).run(transport="streamable-http", host="127.0.0.1", port=int(sys.argv[2]))')
            process = subprocess.Popen([sys.executable, '-c', code, str(root), str(port)],
                cwd=Path(__file__).resolve().parents[1], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                deadline = time.monotonic() + 15
                while True:
                    self.assertIsNone(process.poll(), 'MCP HTTP fixture exited')
                    try:
                        with socket.create_connection(('127.0.0.1', port), .2):
                            break
                    except OSError:
                        if time.monotonic() > deadline:
                            self.fail('MCP HTTP server did not start')
                        time.sleep(.05)
                conn = Connection.preset('mcp_http')
                conn.enabled, conn.base_url = True, f'http://127.0.0.1:{port}/mcp'
                ConnectionStore(root).save('local', [conn])
                service = GenerationService(root)
                self.assertIn('list_stories', [t['name'] for t in mcp_action(service, conn.id)['tools']])
                result = mcp_action(service, conn.id, tool_name='list_stories')
                self.assertIn('HTTP MCP series', json.dumps(result))
                from src.connections.transport import ConnectionError
                with self.assertRaisesRegex(ConnectionError, 'failure'):
                    mcp_action(service, conn.id, tool_name='get_episode', arguments={'episode_path': '../private.json'})
            finally:
                process.terminate()
                process.wait(timeout=10)

    def test_generic_api_actual_local_http(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            server = ProviderFixture(root)
            try:
                conn = Connection.preset('http')
                conn.enabled, conn.base_url = True, server.url
                ConnectionStore(root).save('local', [conn])
                result = call_http(GenerationService(root), conn.id, 'POST', '/endpoint', {'story': 'Ama'})
                self.assertEqual(result['body'], {'story': 'Ama'})
            finally:
                server.close()

    def test_studio_tools_scoped_and_write_opt_in(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            library = StoryLibrary(root)
            story = library.create_story('Ama')
            episode = library.create_episode(story)
            relative = (episode.directory / 'scenes.json').relative_to(root).as_posix()
            operations = StudioTools(root)
            self.assertEqual(operations.get_episode(relative)['episode_id'], 'episode_001')
            with self.assertRaisesRegex(ValueError, 'inside'):
                operations.inside('../private')
            with self.assertRaisesRegex(ValueError, 'disabled'):
                operations.save_script_draft(relative, 'test')
            with self.assertRaisesRegex(ValueError, 'disabled'):
                operations.render(relative)

    @unittest.skipUnless(importlib.util.find_spec('mcp'), 'Optional MCP dependency not installed')
    def test_actual_stdio_mcp_list_call_and_draft(self):
        with tempfile.TemporaryDirectory(prefix='VNS MCP été ') as folder:
            root = Path(folder)
            library = StoryLibrary(root)
            story = library.create_story('Ama MCP')
            episode = library.create_episode(story)
            source = episode.directory / 'scenes.json'
            before = source.read_bytes()
            conn = Connection.preset('mcp_stdio')
            conn.enabled = True
            conn.options = {'command': sys.executable, 'args': ['-m', 'src.studio_mcp', '--workspace', str(root), '--allow-drafts'],
                            'cwd': str(Path(__file__).resolve().parents[1])}
            ConnectionStore(root).save('local', [conn])
            service = GenerationService(root)
            tools = mcp_action(service, conn.id)['tools']
            self.assertIn('save_script_draft', [t['name'] for t in tools])
            self.assertNotIn('render', [t['name'] for t in tools])
            result = mcp_action(service, conn.id, tool_name='list_stories', arguments={})
            self.assertIn('Ama MCP', json.dumps(result))
            result = mcp_action(service, conn.id, tool_name='save_script_draft', arguments={
                'episode_path': source.relative_to(root).as_posix(), 'text': json.dumps(DRAFT), 'structured': True})
            self.assertFalse(result.get('isError', False))
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(len(list((episode.directory / 'drafts').glob('*.json'))), 1)
