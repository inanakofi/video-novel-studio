"""Real local HTTP/media workflow tests. Fixtures are not live AI inference."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image
from src.connections.config import Connection, ConnectionStore
from src.connections.generation import GenerationService
from src.media import ffmpeg
from src.production.adapters import Router, substitute
from src.production.manuscript import extract, chunks
from src.production.runner import ProductionRunner, validate_plan, validate_script
from src.scene_builder import load_episode
from test_media_pipeline import tone


PLAN = {'title': 'The gate', 'premise': 'Ama finds a letter.', 'series_bible': 'CANON: Ama lives near the gate.',
        'style_bible': 'Warm light and blue clothing.', 'audio_bible': 'Clear speech.',
        'characters': [{'id': 'CHAR-001', 'name': 'Ama', 'description': 'Short hair, blue coat.'}],
        'locations': [{'id': 'LOC-001', 'name': 'Gate', 'description': 'A blue gate in a stone wall.'}],
        'episodes': [{'title': 'The letter', 'outline': 'Ama opens a letter at the gate.', 'source_chunks': ['SRC-0001']}]}
SCRIPT = {'title': 'The letter', 'hook': 'Who sent it?', 'cliffhanger': 'The letter says return.',
          'handoff': 'Ama has the letter.', 'shots': [{'text': 'Come home.', 'speaker': 'CHAR-001',
            'characters': ['CHAR-001'], 'location': 'LOC-001', 'seconds': 1.2, 'visual': 'Ama opens the letter.'}]}


def draft(prompt):
    contract = prompt.split('Return ONLY a JSON object using this contract:\n')[-1].split('Production request and source data')[0]
    if '"prompt"' in contract:
        return {'prompt': 'Ama, short hair and a blue coat, opens a letter at the blue gate. Warm light, medium shot, vertical framing.'}
    if '"blocking"' in contract:
        return {'blocking': [], 'warnings': ['Fixture only; media unreviewed.']}
    if '"shots"' in contract:
        return SCRIPT
    if '"episodes"' in contract:
        return PLAN
    return {'summary': 'SRC-0001: Ama discovers a letter at a blue gate.'}


class ProductionFixture:
    def __init__(self, root):
        self.calls = []
        self.fail = False
        self.invalid_text = False
        self.cancel_after = None
        self.cancel_event = None
        image = root / 'fixture.png'
        Image.new('RGB', (120, 200), '#16504a').save(image)
        tone(root / 'fixture.wav', duration=.65)
        ffmpeg(['-f', 'lavfi', '-i', 'testsrc2=size=120x200:rate=30', '-t', '1', '-an', '-c:v', 'libx264', str(root / 'fixture.mp4')])
        self.media = {'.png': image.read_bytes(), '.wav': (root / 'fixture.wav').read_bytes(), '.mp4': (root / 'fixture.mp4').read_bytes()}
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.calls.append((self.path, body))
                if owner.fail:
                    self.send_response(503)
                    self.end_headers()
                    return
                kind = self.path.strip('/')
                if kind == 'story':
                    result = {'text': 'broken JSON' if owner.invalid_text else json.dumps(draft(body['prompt']))}
                else:
                    ext, mime = {'image': ('.png', 'image/png'), 'voice': ('.wav', 'audio/wav'),
                                 'video': ('.mp4', 'video/mp4'), 'lipsync': ('.mp4', 'video/mp4')}[kind]
                    result = {'base64': base64.b64encode(owner.media[ext]).decode(), 'mime_type': mime}
                    if kind == 'lipsync' and body.get('video'):
                        result['base64'] = body['video'].split(',', 1)[1]
                payload = json.dumps(result).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                if owner.cancel_after == len(owner.calls):
                    owner.cancel_event.set()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def configure(self, root):
        profile = Connection('fixture', 'Production fixture', 'http', self.url, 'fixture-model', True,
                             options={'production': {kind: {'path': '/' + kind, 'arguments': {
                                 'prompt': '{{prompt}}', 'request_id': '{{request_id}}', 'model': '{{model}}',
                                 'speaker': '{{speaker}}', 'reference_images': '{{reference_images}}'}}
                                 for kind in ('story', 'image', 'voice', 'video', 'lipsync')}})
        ConnectionStore(root).save('local', [profile])
        return profile


def config(video_format='narrated'):
    return {'title': 'Automated gate', 'format': video_format, 'adaptation': 'faithful', 'episodes': 1,
            'seconds': 15, 'max_calls': 50, 'resolution': 'preview', 'references': False,
            'routes': {r: 'fixture' for r in ('analysis', 'writing', 'review', 'image', 'voice', 'video')}}


class ManuscriptTests(unittest.TestCase):
    def test_all_characters_are_covered_without_overlap_or_truncation(self):
        source = ('Chapter one.\n\nCafé — a new beginning. ' * 1500).strip()
        parts = chunks(source)
        self.assertEqual(''.join(p['text'] for p in parts), source)
        self.assertTrue(all(len(p['text']) <= 12000 for p in parts))
        self.assertEqual(parts[-1]['end'], len(source))

    def test_docx_plain_text_and_xml_entities(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'book.docx'
            xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Ama</w:t></w:r></w:p><w:p><w:r><w:t>Returns</w:t></w:r></w:p></w:body></w:document>'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('word/document.xml', xml)
            self.assertEqual(extract(path), 'Ama\n\nReturns')
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('word/document.xml', '<!DOCTYPE test [<!ENTITY x "bad">]>' + xml)
            with self.assertRaisesRegex(ValueError, 'entity'):
                extract(path)

    def test_contract_validation_and_typed_templates(self):
        invalid = json.loads(json.dumps(PLAN))
        invalid['episodes'][0]['source_chunks'] = ['SRC-9999']
        with self.assertRaisesRegex(ValueError, 'source chunk'):
            validate_plan(invalid, 1, {'SRC-0001'})
        invalid = json.loads(json.dumps(SCRIPT))
        invalid['shots'][0]['location'] = '../../outside'
        with self.assertRaisesRegex(ValueError, 'canonical'):
            validate_script(invalid, PLAN)
        self.assertEqual(substitute({'references': '{{reference_images}}', 'model': '{{model}}'},
                                    {'reference_images': ['data:image/png;base64,a'], 'model': 'fixture'}),
                         {'references': ['data:image/png;base64,a'], 'model': 'fixture'})


class ProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='VNS production fixtures ')
        cls.http = ProductionFixture(Path(cls.temp.name))

    @classmethod
    def tearDownClass(cls):
        cls.http.close()
        cls.temp.cleanup()

    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix='VNS novel été ')
        self.root = Path(self.work.name)
        self.http.calls.clear()
        self.http.fail = self.http.invalid_text = False
        self.http.cancel_after = None
        self.http.configure(self.root)
        self.manuscript = self.root / 'novel.txt'
        self.manuscript.write_text('Ama found a letter at the blue gate. Come home, it said.', encoding='utf-8')
        self.runner = ProductionRunner(self.root)

    def tearDown(self):
        self.work.cleanup()

    def test_all_three_formats_render_real_verified_videos_and_resume_without_calls(self):
        for video_format in ('narrated', 'cartoon', 'cinematic'):
            with self.subTest(video_format=video_format):
                options = config(video_format)
                options['references'] = video_format == 'cartoon'
                state = self.runner.create(self.manuscript, options)
                completed = self.runner.run(state['id'])
                self.assertEqual(completed['status'], 'complete')
                self.assertTrue(completed['exports'][0]['verified'])
                story = self.root / completed['story']
                episode = load_episode(story / 'episodes/episode_001/scenes.json')
                self.assertEqual(episode.scenes[0].media_type, 'image' if video_format == 'narrated' else 'video')
                self.assertTrue(episode.resolve_asset(episode.scenes[0].narration_audio).is_file())
                self.assertTrue((episode.directory / 'subtitles.srt').is_file())
                self.assertNotIn('<!--', (episode.directory / 'script.md').read_text(encoding='utf-8'))
                self.assertEqual(json.loads((episode.directory / 'shot_list.json').read_text(encoding='utf-8'))['shots'][0]['visual'], SCRIPT['shots'][0]['visual'])
                manifest = json.loads((story / 'production_manifest.json').read_text(encoding='utf-8'))
                self.assertEqual(manifest['editorial_approval'], 'pending')
                count = len(self.http.calls)
                self.runner.run(state['id'])
                self.assertEqual(len(self.http.calls), count)
        self.assertTrue(any(isinstance(body.get('reference_images'), list) and body['reference_images'] for _, body in self.http.calls))

    def test_plan_pause_then_resume_only_generates_remaining_stages(self):
        options = config()
        options['pause_after_plan'] = True
        state = self.runner.create(self.manuscript, options)
        paused = self.runner.run(state['id'])
        self.assertEqual(paused['status'], 'awaiting_plan')
        self.assertEqual(len(self.http.calls), 2)
        self.runner.run(state['id'])
        self.assertEqual(len(self.http.calls), 2)
        completed = self.runner.run(state['id'], accept_plan=True)
        self.assertEqual(completed['status'], 'complete')
        self.assertEqual(len([p for p, _ in self.http.calls if p == '/story']), 5)

    def test_paused_plan_can_assign_new_voice_profiles_before_media_generation(self):
        from dataclasses import replace
        options = config()
        options['pause_after_plan'] = True
        state = self.runner.create(self.manuscript, options)
        self.runner.run(state['id'])
        profile = self.http.configure(self.root)
        voice = replace(profile, id='new_voice', name='New character voice', model='chosen-voice')
        ConnectionStore(self.root).save('local', [profile, voice])
        updated = self.runner.update_speakers(state['id'], {'CHAR-001': voice.id})
        self.assertIn(voice.id, updated['connections'])
        self.assertEqual(len(self.http.calls), 2)
        self.assertEqual(self.runner.run(state['id'], accept_plan=True)['status'], 'complete')
        self.assertEqual([body['model'] for path, body in self.http.calls if path == '/voice'], ['chosen-voice'])
        with self.assertRaisesRegex(ValueError, 'paused'):
            self.runner.update_speakers(state['id'], {})

    def test_unknown_tool_outcome_never_resubmits_without_explicit_retry(self):
        state = self.runner.create(self.manuscript, config())
        self.http.fail = True
        with self.assertRaises(Exception):
            self.runner.run(state['id'])
        self.http.fail = False
        with self.assertRaisesRegex(ValueError, 'outcome is unknown'):
            self.runner.run(state['id'])
        self.assertEqual(len(self.http.calls), 1)
        self.runner.retry_stage(state['id'])
        completed = self.runner.run(state['id'])
        self.assertEqual(completed['status'], 'complete')
        self.assertEqual(len(completed['retries']), 1)

    def test_invalid_text_can_be_corrected_without_resubmitting(self):
        state = self.runner.create(self.manuscript, config())
        self.http.invalid_text = True
        with self.assertRaisesRegex(ValueError, 'not complete JSON'):
            self.runner.run(state['id'])
        saved = self.runner.load(state['id'])
        stage = saved['stages'][saved['current_stage']]
        path = self.runner.runs / state['id'] / stage['artifact']
        path.write_text(json.dumps({'summary': 'SRC-0001: Ama finds a letter.'}), encoding='utf-8')
        self.http.invalid_text = False
        self.assertEqual(self.runner.run(state['id'])['status'], 'complete')
        self.assertEqual(len([p for p, _ in self.http.calls if p == '/story']), 5)

    def test_disabled_connections_preflight_and_changed_profile(self):
        profile = self.http.configure(self.root)
        ConnectionStore(self.root).save('disabled', [profile])
        with self.assertRaisesRegex(Exception, 'disabled'):
            self.runner.create(self.manuscript, config())
        self.assertEqual(self.http.calls, [])
        ConnectionStore(self.root).save('local', [profile])
        state = self.runner.create(self.manuscript, config())
        profile.model = 'changed-model'
        ConnectionStore(self.root).save('local', [profile])
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.runner.run(state['id'])
        self.assertEqual(self.http.calls, [])

    def test_tool_output_cannot_import_arbitrary_local_paths(self):
        state = self.runner.create(self.manuscript, config())
        directory = self.runner.runs / state['id']
        router = Router(self.runner.service, state, directory, lambda: None)
        with self.assertRaisesRegex(ValueError, 'inside'):
            router._artifact(directory / 'stages' / 'image', {'path': str(self.manuscript)}, 'image', 'local')

    def test_lipsync_receives_recorded_audio_and_assembled_video(self):
        profile = self.http.configure(self.root)
        profile.options['production']['lipsync']['arguments'].update(audio='{{audio_data_uri}}', video='{{video_data_uri}}')
        ConnectionStore(self.root).save('local', [profile])
        options = config('cartoon')
        options['routes']['lipsync'] = profile.id
        state = self.runner.create(self.manuscript, options)
        self.assertEqual(self.runner.run(state['id'])['status'], 'complete')
        calls = [body for path, body in self.http.calls if path == '/lipsync']
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]['audio'].startswith('data:audio/'))
        self.assertTrue(calls[0]['video'].startswith('data:video/'))

    def test_render_interruption_resumes_without_regenerating_assets(self):
        from src.media import RenderCancelled
        state = self.runner.create(self.manuscript, config())
        cancel = threading.Event()
        def interrupted(*args, **kwargs):
            cancel.set()
            raise RenderCancelled('Fixture interrupted before render')
        with patch('src.production.runner.render_episode', side_effect=interrupted):
            with self.assertRaises(RenderCancelled):
                self.runner.run(state['id'], cancel=cancel)
        self.assertEqual(self.runner.load(state['id'])['status'], 'paused')
        count = len(self.http.calls)
        cancel.clear()
        self.assertEqual(self.runner.run(state['id'], cancel=cancel)['status'], 'complete')
        self.assertEqual(len(self.http.calls), count)

    def test_speaker_override_uses_its_own_model_connection(self):
        from dataclasses import replace
        profile = self.http.configure(self.root)
        voice = replace(profile, id='character_voice', name='Ama voice', model='character-voice-model')
        ConnectionStore(self.root).save('local', [profile, voice])
        options = config()
        options['speaker_routes'] = {'CHAR-001': voice.id}
        state = self.runner.create(self.manuscript, options)
        self.runner.run(state['id'])
        calls = [body for path, body in self.http.calls if path == '/voice']
        self.assertEqual(calls[0]['model'], 'character-voice-model')

    def test_existing_provider_task_resumes_without_new_submission(self):
        from dataclasses import asdict
        from test_connections import ProviderFixture
        server = ProviderFixture(self.root)
        try:
            connection = Connection('runway', 'Video fixture', 'runway', server.url, 'fixture/model', True)
            ConnectionStore(self.root).save('local', [connection])
            directory = self.root / 'router_run'
            directory.mkdir()
            state = {'id': 'router_run', 'stages': {}, 'config': {'routes': {'video': connection.id}},
                     'connections': {connection.id: asdict(connection)}}
            cancel = threading.Event()
            server.cancel_on_submit = cancel
            router = Router(self.runner.service, state, directory, lambda: None, cancel)
            with self.assertRaises(Exception):
                router.generate('clip', 'video', 'video', 'Ama at the gate')
            cancel.clear()
            server.cancel_on_submit = None
            self.assertTrue(router.generate('clip', 'video', 'video', 'Ama at the gate').is_file())
            self.assertEqual(len([c for c in server.calls if c[1] == '/text_to_video']), 1)
        finally:
            server.close()

    def test_call_limit_stops_before_next_submission_and_run_lock_blocks_duplicates(self):
        options = config()
        options['max_calls'] = 5
        state = self.runner.create(self.manuscript, options)
        lock = self.runner.runs / state['id'] / 'running.lock'
        lock.write_text('fixture')
        with self.assertRaisesRegex(ValueError, 'already running'):
            self.runner.run(state['id'])
        lock.unlink()
        with self.assertRaisesRegex(ValueError, 'call limit'):
            self.runner.run(state['id'])
        self.assertEqual(len(self.http.calls), 5)

    @unittest.skipUnless(importlib.util.find_spec('mcp'), 'Optional MCP dependency')
    def test_actual_mcp_stdio_production_route(self):
        server = self.root / 'production_mcp_fixture.py'
        server.write_text('from mcp.server import MCPServer\nserver = MCPServer("production fixture")\n'
                          '@server.tool()\ndef produce(prompt: str, model: str, request_id: str) -> dict:\n'
                          '    return {"text": "A saved MCP production draft"}\n'
                          'server.run(transport="stdio")\n', encoding='utf-8')
        connection = Connection('tool', 'Fixture MCP', 'mcp_stdio', '', 'chosen-model', True,
                                options={'command': sys.executable, 'args': [str(server)], 'production': {
                                    'story': {'tool': 'produce', 'arguments': {'prompt': '{{prompt}}', 'model': '{{model}}', 'request_id': '{{request_id}}'}}}})
        ConnectionStore(self.root).save('local', [connection])
        directory = self.root / 'run'
        directory.mkdir()
        from dataclasses import asdict
        state = {'id': 'test', 'config': {'routes': {'analysis': 'tool'}}, 'stages': {}, 'connections': {'tool': asdict(connection)}}
        router = Router(GenerationService(self.root), state, directory, lambda: None)
        result = router.generate('analyse', 'analysis', 'story', 'Read the manuscript')
        self.assertEqual(result, 'A saved MCP production draft')
        self.assertEqual(router.generate('analyse', 'analysis', 'story', 'Read the manuscript'), result)


@unittest.skipUnless(os.environ.get('VNS_GUI_TESTS') == '1', 'Set VNS_GUI_TESTS=1 for production desktop')
class ProductionDesktopTests(unittest.TestCase):
    def test_attach_route_produce_and_open_generated_episode(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from src.app import StudioWindow
        import time
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        with tempfile.TemporaryDirectory(prefix='VNS production UI ') as folder:
            root = Path(folder)
            server = ProductionFixture(root)
            workspace = root / 'workspace'
            workspace.mkdir()
            server.configure(workspace)
            source = root / 'book.txt'
            source.write_text('Ama found a letter.', encoding='utf-8')
            window = StudioWindow(workspace)
            window.show()
            try:
                window.tabs.setCurrentIndex(9)
                window.production_source.setText(str(source))
                window.production_title.setText('UI production')
                window.production_seconds.setValue(15)
                for role in ('analysis', 'image', 'voice'):
                    picker = window.production_routes[role]
                    picker.setCurrentIndex(picker.findData('fixture'))
                QTest.mouseClick(window.production_start, Qt.MouseButton.LeftButton)
                deadline = time.monotonic() + 90
                while window._thread is not None and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.02)
                self.assertIsNone(window._thread)
                self.assertFalse(window.last_error, window.last_error)
                self.assertEqual(window.production_runner.list_runs()[0]['status'], 'complete')
                self.assertEqual(window.episode.title, 'The letter')
                self.assertEqual(window.production_prompt_picker.count(), 35)
                capture = os.environ.get('VNS_PRODUCTION_SCREENSHOT')
                if capture:
                    window.production_pages.setCurrentIndex(0)
                    app.processEvents()
                    window.grab().save(capture)
            finally:
                if window._thread:
                    window._cancel.set()
                    while window._thread:
                        app.processEvents()
                        time.sleep(.02)
                window.close()
                app.processEvents()
                server.close()


if __name__ == '__main__':
    unittest.main()
