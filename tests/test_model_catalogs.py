"""Complete provider catalogs and recovery behavior, without billable requests."""
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from src.connections.config import Connection, ConnectionStore
from src.connections.discovery import discover_models, RUNWAY_VIDEO_MODELS
from src.connections.generation import GenerationService
from src.connections.models import ModelCatalog, filter_models, normalize_model
from src.connections.transport import ConnectionError
from src.media import RenderCancelled


class FakeTransport:
    def __init__(self, provider, responses, options=None):
        self.connection = replace(Connection.preset(provider), enabled=True, options=options or {})
        self.responses = responses
        self.calls = []

    def request(self, method, path):
        self.calls.append((method, path))
        value = self.responses[path]
        if isinstance(value, Exception):
            raise value
        return value


class CatalogDiscoveryTests(unittest.TestCase):
    def test_entire_multimodal_catalog_without_item_limit(self):
        raw = [{'id': f'{kind}-{i}', 'architecture': {'output_modalities': [kind]}}
               for kind in ('text', 'speech', 'image', 'video') for i in range(210)]
        transport = FakeTransport('openrouter', {'/models?output_modalities=all': {'data': raw}})
        result = discover_models(transport)
        self.assertEqual(len(result['models']), 840)
        for task in ('story', 'script', 'image', 'voice', 'video'):
            self.assertEqual(len(filter_models(result['catalog'], task)), 210)

    def test_compatible_pagination_deduplication_and_unknown_modalities(self):
        transport = FakeTransport('openai_compatible', {
            '/models': {'data': [{'id': 'a'}], 'has_more': True, 'last_id': 'a'},
            '/models?after=a': {'data': [{'id': 'a'}, None, {'id': 'b'}], 'has_more': False}})
        result = discover_models(transport)
        self.assertEqual(result['models'], ['a', 'b'])
        self.assertEqual(len(filter_models(result['catalog'], 'voice')), 2)
        self.assertFalse(result['catalog'][0]['modalities_known'])

    def test_failed_or_looping_discovery_keeps_existing_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            service = GenerationService(folder)
            transport = FakeTransport('openai_compatible', {'/models': {'error': 'bad response'}})
            old = [normalize_model({'id': 'saved-model'}, 'openai_compatible')]
            service.catalog.save(transport.connection, old)
            with patch.object(service, 'transport', return_value=transport):
                with self.assertRaises(ConnectionError):
                    service.discover(transport.connection.id)
                transport.responses = {
                    '/models': {'data': [{'id': 'a'}], 'has_more': True},
                    '/models?after=a': {'data': [{'id': 'a'}], 'has_more': True}}
                with self.assertRaisesRegex(ConnectionError, 'pagination'):
                    service.discover(transport.connection.id)
            self.assertEqual(service.catalog.records(transport.connection), old)

    def test_elevenlabs_lists_only_synthesis_models_even_when_voices_forbidden(self):
        transport = FakeTransport('elevenlabs', {
            '/models': [{'model_id': 'tts-one', 'can_do_text_to_speech': True},
                        {'model_id': 'tts-two', 'can_do_text_to_speech': True},
                        {'model_id': 'transcribe', 'can_do_text_to_speech': False}],
            '/voices': ConnectionError('Voice permission denied')})
        result = discover_models(transport)
        self.assertEqual(result['models'], ['tts-one', 'tts-two'])
        self.assertEqual(len(filter_models(result['catalog'], 'voice')), 2)
        self.assertEqual(filter_models(result['catalog'], 'story'), [])
        self.assertIn('voice_warning', result['response'])

    def test_comfy_workflow_model_inputs_intersect_and_preserve_filename_substitution(self):
        info = {'Loader': {'input': {'required': {'ckpt_name': [['models/a.safetensors', 'models/b.safetensors']]}}},
                'OtherLoader': {'input': {'required': {'ckpt_name': [['b.safetensors', 'c.safetensors']]}}},
                'VAELoader': {'input': {'required': {'vae_name': [['not-a-checkpoint.safetensors']]}}}}
        workflow = {'1': {'class_type': 'Loader', 'inputs': {'ckpt_name': 'models/{{model}}'}},
                    '2': {'class_type': 'OtherLoader', 'inputs': {'ckpt_name': '{{model}}'}},
                    '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'fixed.safetensors'}}}
        transport = FakeTransport('comfyui', {'/object_info': info}, {'workflow': workflow})
        self.assertEqual(discover_models(transport)['models'], ['b.safetensors'])

    def test_runway_catalog_is_labelled_as_documented_suggestions(self):
        result = discover_models(FakeTransport('runway', {'/organization': {'credits': 0}}))
        self.assertEqual(result['models'], list(RUNWAY_VIDEO_MODELS))
        self.assertIn('account access not verified', result['status'])
        self.assertEqual(filter_models(result['catalog'], 'voice'), [])

    def test_custom_model_lists_support_lipsync_and_are_isolated_by_connection(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog = ModelCatalog(folder)
            connection = replace(Connection.preset('http'), options={'models': [
                {'id': 'sync', 'tasks': ['lipsync'], 'output_modalities': ['video']},
                {'id': 'writer', 'tasks': ['story'], 'output_modalities': ['text']}]})
            self.assertEqual([r['id'] for r in filter_models(catalog.records(connection), 'lipsync')], ['sync'])
            catalog.save(connection, [normalize_model({'id': 'private'}, 'http')])
            self.assertEqual(catalog.records(replace(connection, id='different', options={})), [])

    def test_malformed_optional_metadata_and_unknown_speech_price(self):
        self.assertIsNone(normalize_model(None, 'openrouter'))
        record = normalize_model({'id': 'unknown', 'architecture': [], 'pricing': [], 'name': []}, 'openrouter')
        self.assertFalse(record['free'])
        self.assertFalse(record['modalities_known'])
        speech = normalize_model({'id': 'speech', 'output_modalities': ['speech'],
                                  'pricing': {'prompt': '0', 'completion': '0'}}, 'openrouter')
        self.assertFalse(speech['free'])

    def test_damaged_cached_names_and_tasks_are_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog = ModelCatalog(folder)
            conn = Connection.preset('openrouter')
            good = normalize_model({'id': 'good', 'output_modalities': ['text']}, conn.provider)
            catalog.save(conn, [good, {**good, 'id': 'broken-name', 'name': []},
                                {**good, 'id': 'broken-task', 'tasks': None}])
            self.assertEqual(catalog.records(conn), [good])

    def test_bulk_refresh_deduplicates_public_catalog_and_cancellation_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            service = GenerationService(folder)
            a = replace(Connection.preset('openrouter'), enabled=True)
            ConnectionStore(folder).save('online', [a, replace(a, id='other')])
            with patch.object(service, 'discover', return_value={'catalog': [], 'status': 'complete'}) as discover:
                service.refresh_catalogs()
                self.assertEqual(discover.call_count, 1)
                cancel = threading.Event()
                cancel.set()
                with self.assertRaises(RenderCancelled):
                    service.refresh_catalogs(cancel)


@unittest.skipUnless(os.environ.get('VNS_GUI_TESTS') == '1', 'Set VNS_GUI_TESTS=1 for model picker checks')
class ModelCatalogDesktopTests(unittest.TestCase):
    def test_show_all_restores_every_task_and_keeps_saved_models(self):
        from PySide6.QtWidgets import QApplication
        from src.app import StudioWindow
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            conn = replace(Connection.preset('openrouter'), enabled=True)
            ConnectionStore(root).save('online', [conn])
            records = [normalize_model({'id': f'{kind}-{i}', 'output_modalities': [kind]}, conn.provider)
                       for kind in ('text', 'image', 'speech', 'video') for i in range(220)]
            ModelCatalog(root).save(conn, records)
            window = StudioWindow(root)
            try:
                for role in ('analysis', 'writing', 'review', 'image', 'voice', 'video'):
                    route = window.production_routes[role]
                    route.setCurrentIndex(route.findData(conn.id))
                window.production_models['analysis'].setEditText('text-219')
                window.production_free.setChecked(True)
                window.production_open.setChecked(True)
                window._show_all_production_models()
                for role in ('analysis', 'writing', 'review', 'image', 'voice', 'video'):
                    self.assertEqual(window.production_models[role].count(), 221)
                    self.assertEqual(window.production_model_counts[role].text(), '220 / 220 models')
                self.assertEqual(window.production_models['analysis'].currentText(), 'text-219')
                window.connection_free.setChecked(True)
                window.generation_kind.setCurrentText('voice')
                window._show_all_connection_models()
                self.assertEqual(window.generation_model.count(), 221)
                self.assertIn('220 of 220', window.generation_model_notice.text())
            finally:
                window.close()
                window.deleteLater()
                app.processEvents()
