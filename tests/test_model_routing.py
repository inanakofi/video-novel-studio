"""Model overrides must use the chosen key, capability and saved recovery state."""
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

from src.connections.config import Connection, ConnectionStore, SecretStore
from src.connections.generation import GenerationService
from src.connections.models import ModelCatalog, filter_models, normalize_model
from src.connections.transport import ConnectionError
from src.production.adapters import Router
from src.production.runner import ProductionRunner
from test_connections import ProviderFixture
from test_production import config


def record(model_id, inputs, outputs, **extra):
    return {'id': model_id, 'architecture': {'input_modalities': inputs, 'output_modalities': outputs}, **extra}


CATALOG = [record('text-a:free', ['text'], ['text'], hugging_face_id='org/text'),
           record('text-b:free', ['text', 'image'], ['text']),
           record('image-free', ['text'], ['image'], pricing={'prompt': '0', 'image_output': '0'}, hugging_face_id='org/image'),
           record('speech:free', ['text'], ['speech']),
           record('video-paid', ['text', 'image'], ['video'], pricing={'prompt': '0', 'completion': '0'})]


class CatalogTests(unittest.TestCase):
    def test_output_modalities_price_and_open_weights_are_independent(self):
        records = [normalize_model(r, 'openrouter') for r in CATALOG]
        self.assertEqual([r['id'] for r in filter_models(records, 'image')], ['image-free'])
        self.assertEqual([r['id'] for r in filter_models(records, 'image', free=True, open_weights=True)], ['image-free'])
        self.assertEqual([r['id'] for r in filter_models(records, 'voice', free=True)], ['speech:free'])
        self.assertEqual(filter_models(records, 'video', free=True), [])
        self.assertFalse(filter_models(records, 'video')[0]['free'])

    def test_catalog_shared_by_same_endpoint_but_isolated_from_other_servers(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog = ModelCatalog(folder)
            a = Connection.preset('openrouter')
            b = replace(a, id='other-key')
            c = replace(a, base_url='https://different.example/v1')
            catalog.save(a, [normalize_model(r, a.provider) for r in CATALOG])
            self.assertEqual(catalog.records(a), catalog.records(b))
            self.assertEqual(catalog.records(c), [])

    def test_corrupt_optional_catalog_is_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog = ModelCatalog(folder)
            connection = Connection.preset('openrouter')
            catalog.path.write_text(json.dumps({catalog.key(connection): []}), encoding='utf-8')
            self.assertEqual(catalog.records(connection), [])


class ModelRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.server = ProviderFixture(Path(cls.temp.name))

    @classmethod
    def tearDownClass(cls):
        cls.server.close()
        cls.temp.cleanup()

    def setUp(self):
        self.work = tempfile.TemporaryDirectory(dir=self.temp.name)
        self.root = Path(self.work.name)
        self.server.calls.clear()
        self.server.models = CATALOG
        self.server.pending = self.server.fail = self.server.invalid_media = False
        self.server.cancel_on_submit = None
        self.connection = Connection('shared', 'Shared platform', 'openrouter', self.server.url,
                                     'text-a:free', True)
        self.secrets = SecretStore(self.root / 'vault')
        self.service = GenerationService(self.root, self.secrets)
        ConnectionStore(self.root).save('local', [self.connection])
        self.service.discover('shared')
        self.server.calls.clear()

    def tearDown(self):
        self.work.cleanup()

    def test_single_key_generates_different_text_image_voice_models_without_mutation(self):
        self.secrets.put('shared', 'fixture-shared-key')
        for kind, model in [('story', 'text-b:free'), ('image', 'image-free'), ('voice', 'speech:free')]:
            job = self.service.run('shared', kind, 'A rainy street in Osu.', model=model)
            self.assertEqual(job['status'], 'ready')
            self.assertEqual(job['connection']['model'], model)
            self.assertNotIn('fixture-shared-key', json.dumps(job))
        self.assertEqual([c[3]['model'] for c in self.server.calls], ['text-b:free', 'image-free', 'speech:free'])
        self.assertTrue(all(c[2]['Authorization'] == 'Bearer fixture-shared-key' for c in self.server.calls))
        self.assertEqual(self.service.connection('shared')[1].model, 'text-a:free')

    def test_same_model_can_serve_multiple_tasks_and_different_connection_uses_other_key(self):
        self.secrets.put('shared', 'first-fixture-key')
        other = replace(self.connection, id='other', name='Other key')
        self.secrets.put('other', 'second-fixture-key')
        ConnectionStore(self.root).save('local', [self.connection, other])
        self.service.run('shared', 'story', 'One', model='text-b:free')
        self.service.run('shared', 'script', 'Two', model='text-b:free')
        self.service.run('other', 'story', 'Three', model='text-b:free')
        self.assertEqual([c[2]['Authorization'] for c in self.server.calls],
                         ['Bearer first-fixture-key', 'Bearer first-fixture-key', 'Bearer second-fixture-key'])

    def test_rejects_text_only_vision_model_for_illustration_before_request(self):
        with self.assertRaisesRegex(ValueError, 'cannot generate image'):
            self.service.run('shared', 'image', 'Rain', model='text-b:free')
        self.assertEqual(self.server.calls, [])

    def test_override_video_resumes_with_saved_model_and_single_submission(self):
        cancel = threading.Event()
        self.server.cancel_on_submit = cancel
        with self.assertRaises(ConnectionError):
            self.service.run('shared', 'video', 'Rain', model='video-paid', cancel=cancel)
        job = self.service.list_jobs()[0]
        self.assertEqual(job['remote_id'], 'fixture-video')
        self.server.cancel_on_submit = None
        complete = self.service.run('shared', 'video', 'Rain', resume=job['id'])
        self.assertEqual(complete['status'], 'ready')
        self.assertEqual(complete['connection']['model'], 'video-paid')
        self.assertEqual(len([c for c in self.server.calls if c[0] == 'POST']), 1)

    def test_production_router_uses_role_overrides_and_original_connection_snapshot(self):
        cfg = config()
        cfg['routes'] = {r: 'shared' for r in cfg['routes']}
        cfg['models'] = {'analysis': 'text-a:free', 'writing': 'text-b:free', 'review': 'text-a:free',
                         'image': 'image-free', 'voice': 'speech:free'}
        runner = ProductionRunner(self.root, self.service)
        snapshots = runner.preflight(cfg)
        self.assertEqual(snapshots['shared']['model'], 'text-a:free')
        state = {'id': 'run', 'config': cfg, 'connections': snapshots, 'stages': {}}
        directory = self.root / 'run'
        directory.mkdir()
        router = Router(self.service, state, directory, lambda: None)
        router.generate('analysis', 'analysis', 'story', 'Analyse')
        router.generate('writing', 'writing', 'story', 'Write')
        self.assertEqual([c[3]['model'] for c in self.server.calls], ['text-a:free', 'text-b:free'])
        cfg['models']['image'] = 'text-a:free'
        with self.assertRaisesRegex(ValueError, 'cannot generate image'):
            runner.preflight(cfg)

    def test_production_preflight_accepts_task_voice_without_profile_default(self):
        speech = Connection('speech', 'Speech', 'elevenlabs', self.server.url, 'tts-one', True)
        ConnectionStore(self.root).save('local', [self.connection, speech])
        cfg = config()
        cfg['routes'] = {r: 'shared' for r in cfg['routes']}
        cfg['routes']['voice'] = 'speech'
        cfg['models'] = {'image': 'image-free'}
        cfg['voices'] = {'voice': 'chosen-voice'}
        snapshots = ProductionRunner(self.root, self.service).preflight(cfg)
        self.assertNotIn('voice_id', snapshots['speech']['options'])
        state = {'id': 'voice-run', 'config': cfg, 'connections': snapshots, 'stages': {}}
        directory = self.root / 'voice-run'
        directory.mkdir()
        Router(self.service, state, directory, lambda: None).generate('voice', 'voice', 'voice', 'Hello')
        self.assertIn('/text-to-speech/chosen-voice', self.server.calls[-1][1])

    def test_changed_base_profile_still_blocks_resume(self):
        cancel = threading.Event()
        self.server.cancel_on_submit = cancel
        with self.assertRaises(ConnectionError):
            self.service.run('shared', 'video', 'Rain', model='video-paid', cancel=cancel)
        job = self.service.list_jobs()[0]
        ConnectionStore(self.root).save('local', [replace(self.connection, model='text-b:free')])
        with self.assertRaisesRegex(ValueError, 'original connection settings'):
            self.service.run('shared', 'video', 'Rain', resume=job['id'])

    def test_legacy_job_still_blocks_changed_connection_before_resume(self):
        job = self.service.run('shared', 'story', 'One')
        del job['base_connection']
        from src.media import atomic_json
        atomic_json(self.service.jobs / job['id'] / 'job.json', job)
        ConnectionStore(self.root).save('local', [replace(self.connection, model='text-b:free')])
        with self.assertRaisesRegex(ValueError, 'original connection settings'):
            self.service.run('shared', 'story', 'One', resume=job['id'])


@unittest.skipUnless(os.environ.get('VNS_GUI_TESTS') == '1', 'Set VNS_GUI_TESTS=1 for desktop model routing')
class ModelRoutingDesktopTests(unittest.TestCase):
    def test_task_models_filters_shared_key_duplication_and_saved_choices(self):
        from PySide6.QtWidgets import QApplication
        from src.app import StudioWindow
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            connection = Connection('shared', 'One platform', 'openrouter', 'https://openrouter.ai/api/v1',
                                    'text-a:free', True)
            ConnectionStore(root).save('online', [connection])
            ModelCatalog(root).save(connection, [normalize_model(r, connection.provider) for r in CATALOG])
            window = StudioWindow(root)
            try:
                window.secret_store = SecretStore(root / 'vault')
                window.generation_service.secrets = window.secret_store
                window.secret_store.put('shared', 'fixture-ui-key')
                window.production_routes['analysis'].setCurrentIndex(window.production_routes['analysis'].findData('shared'))
                window.production_models['analysis'].setEditText('text-b:free')
                window._use_analysis_platform()
                cfg = window._production_config()
                self.assertEqual(cfg['models']['writing'], 'text-b:free')
                self.assertEqual(cfg['models']['review'], 'text-b:free')
                self.assertEqual(cfg['models']['image'], 'image-free')
                self.assertEqual(cfg['models']['voice'], 'speech:free')
                self.assertEqual(cfg['models']['video'], 'video-paid')
                window.production_free.setChecked(True)
                window.production_open.setChecked(True)
                self.assertEqual(window.production_models['image'].count(), 2)  # blank/default + matching open model
                self.assertEqual(window.production_models['voice'].count(), 1)  # no speech weights metadata
                # Filters narrow suggestions without silently replacing an explicit choice.
                self.assertEqual(window.production_models['voice'].currentText(), 'speech:free')
                window._save_production_choices()
                window._duplicate_connection()
                profiles = ConnectionStore(root).load()[1]
                self.assertEqual(len(profiles), 2)
                self.assertEqual(window.secret_store.get(profiles[1]), 'fixture-ui-key')
                self.assertNotIn('fixture-ui-key', ConnectionStore(root).path.read_text())
                window.close()
                window = StudioWindow(root)
                self.assertEqual(window.production_models['writing'].currentText(), 'text-b:free')
                self.assertEqual(window.production_routes['image'].currentData(), 'shared')
                self.assertTrue(window.production_free.isChecked())
                window.generation_connection.setCurrentIndex(window.generation_connection.findData('shared'))
                window.generation_kind.setCurrentText('image')
                self.assertIn('image-free', [window.generation_model.itemText(i) for i in range(window.generation_model.count())])
                self.assertNotIn('text-b:free', [window.generation_model.itemText(i) for i in range(window.generation_model.count())])
            finally:
                window.close()
                app.processEvents()
