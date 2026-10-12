"""Provider protocol fixtures, not claims of live AI generation."""
from dataclasses import replace
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from PIL import Image
from src.connections.config import Connection, ConnectionStore, SecretStore
from src.connections.generation import GenerationService, parse_script, episode_from_draft
from src.connections.transport import ConnectionError, Transport, validate_url
from src.media import ffmpeg
from src.scene_builder import save_episode, load_episode
from test_media_pipeline import fixture, tone


DRAFT = {'title': 'Ama returns', 'hook': 'A letter arrives.', 'cliffhanger': 'Who sent it?',
         'scenes': [{'narration': 'Ama opened the gate.', 'duration_seconds': 4,
                     'visual_description': 'A blue gate at night.'}]}


class ProviderFixture:
    def __init__(self, root):
        self.calls = []
        self.fail = False
        self.pending = False
        self.invalid_text = False
        self.cancel_on_submit = None
        self.invalid_media = False
        self.models = None
        self.media = {}
        image = root / 'fixture.png'
        Image.new('RGB', (120, 200), '#156050').save(image)
        tone(root / 'fixture.wav')
        ffmpeg(['-i', str(root / 'fixture.wav'), str(root / 'fixture.mp3')])
        ffmpeg(['-f', 'lavfi', '-i', 'testsrc2=size=120x200:rate=30', '-t', '1', '-an', '-c:v', 'libx264', str(root / 'fixture.mp4')])
        self.media = {'.png': image.read_bytes(), '.mp3': (root / 'fixture.mp3').read_bytes(), '.mp4': (root / 'fixture.mp4').read_bytes()}
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.respond()
            def do_POST(self):
                self.respond()
            def respond(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length']))) if self.headers.get('Content-Length') else None
                owner.calls.append((self.command, self.path, dict(self.headers), body))
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', owner.url + '/models')
                    self.end_headers()
                    return
                if owner.fail:
                    self.send_response(429)
                    self.end_headers()
                    return
                content = None
                result = {}
                if self.path.split('?')[0] == '/models':
                    result = {'data': owner.models if owner.models is not None else [{'id': 'fixture/model'}]}
                elif self.path in ('/images', '/images/generations'):
                    result = {'data': [{'b64_json': base64.b64encode(owner.media['.png']).decode(), 'media_type': 'image/png'}], 'usage': {'cost': 0}}
                elif self.path == '/audio/speech':
                    content = b'not audio' if owner.invalid_media else owner.media['.mp3']
                elif self.path == '/videos':
                    result = {'id': 'fixture-video'}
                    if owner.cancel_on_submit:
                        owner.cancel_on_submit.set()
                elif self.path == '/videos/fixture-video':
                    result = {'status': 'pending'} if owner.pending else {'status': 'completed', 'usage': {'cost': 0}}
                elif self.path == '/videos/fixture-video/content':
                    content = owner.media['.mp4']
                elif self.path == '/api/tags':
                    result = {'models': [{'name': 'fixture-local'}]}
                elif self.path == '/chat/completions':
                    result = {'id': 'fixture-generation', 'choices': [{'finish_reason': 'stop', 'message': {'content': 'invalid JSON' if owner.invalid_text else json.dumps(DRAFT)}}], 'usage': {'total_tokens': 34, 'cost': .01}}
                elif self.path == '/api/generate':
                    result = {'response': json.dumps(DRAFT), 'done': True}
                elif self.path.startswith('/text-to-speech/'):
                    content = b'not an audio file' if owner.invalid_media else owner.media['.mp3']
                elif self.path == '/text_to_video':
                    result = {'id': 'fixture-task'}
                    if owner.cancel_on_submit:
                        owner.cancel_on_submit.set()
                elif self.path.startswith('/tasks/'):
                    result = {'status': 'RUNNING'} if owner.pending else {'status': 'SUCCEEDED', 'output': [owner.url + '/video.mp4']}
                elif self.path == '/prompt':
                    result = {'prompt_id': 'fixture-prompt', 'node_errors': {}}
                elif self.path.startswith('/history/'):
                    result = {} if owner.pending else {'fixture-prompt': {'status': {'completed': True}, 'outputs': {'9': {'images': [{'filename': 'fixture.png', 'subfolder': '', 'type': 'output'}]}}}}
                elif self.path.startswith('/view'):
                    content = owner.media['.png']
                elif self.path == '/video.mp4':
                    content = owner.media['.mp4']
                else:
                    result = {'ok': True, 'body': body}
                content = content if content is not None else json.dumps(result).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class ConnectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='VNS connectors été ')
        cls.base = Path(cls.temp.name)
        cls.http = ProviderFixture(cls.base)

    @classmethod
    def tearDownClass(cls):
        cls.http.close()
        cls.temp.cleanup()

    def setUp(self):
        self.work = tempfile.TemporaryDirectory(dir=self.base)
        self.root = Path(self.work.name)
        self.http.calls.clear()
        self.http.fail = self.http.pending = self.http.invalid_text = False
        self.http.cancel_on_submit = None
        self.http.invalid_media = False
        self.store = ConnectionStore(self.root)
        self.secrets = SecretStore(self.root / 'vault')
        self.service = GenerationService(self.root, self.secrets)

    def tearDown(self):
        self.work.cleanup()

    def configure(self, provider, options=None):
        conn = Connection.preset(provider)
        conn.base_url, conn.enabled, conn.model = self.http.url, True, 'fixture/model'
        if options is not None:
            conn.options = options
        self.store.save('local', [conn])
        return conn

    def test_offline_denied_before_transport_or_dns(self):
        conn = self.configure('openrouter')
        self.store.save('disabled', [conn])
        with patch('socket.getaddrinfo', side_effect=AssertionError('Network forbidden')):
            with self.assertRaisesRegex(ConnectionError, 'disabled'):
                self.service.discover(conn.id)
        self.assertEqual(self.http.calls, [])
        self.assertEqual(ConnectionStore(self.root / 'new').load(), ('disabled', []))

    def test_local_mode_and_https_and_credentials_origin(self):
        for url in ('https://example.com', 'http://localhost.evil', 'http://user:secret@localhost', 'file:///etc/passwd'):
            with self.assertRaises(ConnectionError):
                validate_url(url, 'local')
        with self.assertRaises(ConnectionError):
            validate_url('http://example.com', 'online')
        conn = self.configure('openrouter')
        transport = Transport(conn, 'online', 'test-only')
        with self.assertRaisesRegex(ConnectionError, 'another origin'):
            transport._open('GET', 'https://example.com/steal', None, True)

    def test_redirects_are_not_followed(self):
        conn = self.configure('openrouter')
        with self.assertRaisesRegex(ConnectionError, '302'):
            self.service.transport(conn.id).request('GET', '/redirect')
        self.assertEqual([c[1] for c in self.http.calls], ['/redirect'])

    def test_cancel_during_submission_still_saves_provider_id(self):
        conn = self.configure('runway')
        cancel = threading.Event()
        self.http.cancel_on_submit = cancel
        with self.assertRaises(ConnectionError):
            self.service.run(conn.id, 'video', 'A gate', cancel=cancel)
        job = self.service.list_jobs()[0]
        self.assertEqual(job['remote_id'], 'fixture-task')
        self.assertEqual(job['status'], 'waiting')
        self.assertEqual(len(self.http.calls), 1)

    def test_invalid_download_is_not_a_completed_generation(self):
        conn = self.configure('elevenlabs', {'voice_id': 'fixture'})
        self.http.invalid_media = True
        with self.assertRaises(ConnectionError):
            self.service.run(conn.id, 'voice', 'Sample narration')
        job = self.service.list_jobs()[0]
        self.assertNotEqual(job['status'], 'ready')
        self.assertFalse(job['artifacts'])

    def test_openrouter_discovery_and_structured_script(self):
        conn = self.configure('openrouter')
        self.assertEqual(self.service.discover(conn.id)['models'], ['fixture/model'])
        job = self.service.run(conn.id, 'script', 'Draft this episode')
        self.assertEqual(job['status'], 'ready')
        self.assertTrue(job['script_valid'])
        self.assertEqual(job['usage']['total_tokens'], 34)
        call = self.http.calls[-1]
        self.assertEqual(call[1], '/chat/completions')
        self.assertEqual(call[3]['model'], 'fixture/model')
        self.assertFalse(call[3]['stream'])
        self.assertEqual(call[2]['X-Title'], 'Video Novel Studio')
        self.assertFalse((self.root / 'stories').exists())  # A result cannot edit a story.

    def test_preassigned_id_rechecks_under_lock_and_preserves_completed_job(self):
        conn = self.configure('openrouter')
        completed = self.service.run(conn.id, 'story', 'Draft this', job_id='production-stage')
        path = self.service.jobs / 'production-stage' / 'job.json'
        before = path.read_bytes()
        exists = Path.exists
        checks = [0]
        def stale_first_check(candidate):
            if candidate == path:
                checks[0] += 1
                if checks[0] == 1:
                    return False  # Simulate a submission completing just after this check.
            return exists(candidate)
        with patch.object(Path, 'exists', stale_first_check):
            with self.assertRaisesRegex(ValueError, 'already exists'):
                self.service.run(conn.id, 'story', 'Draft again', job_id='production-stage')
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(completed['status'], 'ready')
        self.assertEqual(len([c for c in self.http.calls if c[1] == '/chat/completions']), 1)

    def test_ollama_and_compatible_dialects(self):
        for provider in ('ollama', 'openai_compatible'):
            conn = self.configure(provider)
            self.assertEqual(self.service.run(conn.id, 'script', 'test')['status'], 'ready')
        self.assertIn('/api/generate', [c[1] for c in self.http.calls])

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI')
    def test_encrypted_credentials_and_delete(self):
        conn = self.configure('openrouter')
        secret = 'fixture-secret-never-real'
        self.secrets.put(conn.id, secret)
        self.assertEqual(self.secrets.get(conn), secret)
        self.assertNotIn(secret.encode(), self.secrets._path(conn.id).read_bytes())
        job = self.service.run(conn.id, 'script', 'test')
        self.assertEqual(self.http.calls[-1][2]['Authorization'], 'Bearer ' + secret)
        self.assertNotIn(secret, json.dumps(job))
        self.assertNotIn(secret, self.store.path.read_text())
        self.secrets.delete(conn.id)
        self.assertFalse(self.secrets.exists(conn))

    def test_failure_no_retry_or_ready_job(self):
        conn = self.configure('openrouter')
        self.http.fail = True
        with self.assertRaisesRegex(ConnectionError, '429'):
            self.service.run(conn.id, 'script', 'test')
        self.assertEqual(len(self.http.calls), 1)
        job = self.service.list_jobs()[0]
        self.assertEqual(job['status'], 'failed_or_unknown')
        with self.assertRaisesRegex(ValueError, 'no provider task ID'):
            self.service.run(conn.id, 'script', 'test', resume=job['id'])
        self.assertEqual(len(self.http.calls), 1)

    def test_invalid_json_is_reviewable_but_not_applicable(self):
        conn = self.configure('openrouter')
        self.http.invalid_text = True
        job = self.service.run(conn.id, 'script', 'test')
        self.assertFalse(job['script_valid'])
        with self.assertRaises(ValueError):
            parse_script('invalid JSON')

    def test_real_audio_file_received_and_validated(self):
        conn = self.configure('elevenlabs', {'voice_id': 'fixture voice'})
        job = self.service.run(conn.id, 'voice', 'Sample text')
        self.assertEqual(job['status'], 'ready')
        self.assertTrue((self.service.jobs / job['id'] / 'narration.mp3').is_file())
        self.assertIn('fixture%20voice', self.http.calls[-1][1])

    def test_comfy_workflow_substitution_and_media_download(self):
        conn = self.configure('comfyui', {'workflow': {'1': {'class_type': 'CLIPTextEncode', 'inputs': {'text': '{{prompt}}'}}}})
        job = self.service.run(conn.id, 'image', 'Blue gate')
        self.assertEqual(job['status'], 'ready')
        self.assertEqual(self.http.calls[0][3]['prompt']['1']['inputs']['text'], 'Blue gate')
        self.assertEqual(job['artifacts'], ['output_001.png'])

    def test_interrupted_video_job_resumes_without_second_post(self):
        conn = self.configure('runway')
        self.http.pending = True
        cancel = threading.Event()
        def progress(fraction, message):
            if message.startswith('Job submitted'):
                cancel.set()
        with self.assertRaises(ConnectionError):
            self.service.run(conn.id, 'video', 'A gate', cancel=cancel, progress=progress)
        job = self.service.list_jobs()[0]
        self.assertEqual(job['remote_id'], 'fixture-task')
        self.assertEqual(job['status'], 'waiting')
        self.http.pending = False
        job = self.service.run(conn.id, 'video', 'A gate', resume=job['id'])
        self.assertEqual(job['status'], 'ready')
        self.assertEqual(sum(c[1] == '/text_to_video' for c in self.http.calls), 1)
        download = next(c for c in self.http.calls if c[1] == '/video.mp4')
        self.assertNotIn('Authorization', download[2])

    def test_script_apply_never_uses_model_paths_or_stale_voice(self):
        episode = fixture(self.root / 'episode')
        data = json.loads(json.dumps(DRAFT))
        data['scenes'][0]['visual_asset'] = '../../private.txt'
        revised = episode_from_draft(episode, json.dumps(data))
        self.assertEqual(revised.scenes[0].visual_asset, episode.scenes[0].visual_asset)
        self.assertIsNone(revised.scenes[0].narration_audio)
        self.assertEqual(revised.settings['narration_asset'], 'narration_required.wav')
        save_episode(revised)
        self.assertEqual(load_episode(revised.directory / 'scenes.json').title, 'Ama returns')

    def test_config_rejects_plaintext_secret_options(self):
        conn = self.configure('openrouter')
        conn.options = {'headers': {'Authorization': 'bad'}}
        with self.assertRaisesRegex(ValueError, 'secure credential'):
            self.store.save('online', [conn])


if __name__ == '__main__':
    unittest.main()
