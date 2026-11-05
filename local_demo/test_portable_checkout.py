"""A fresh checkout must not need a neighbour's credentials or private data."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server import ReadOnlyLabels
from ai_execution import ROOT, BASE_URL, MODEL, load_web_config


class PortableCheckoutTests(unittest.TestCase):
    def test_empty_catalog_is_readable_without_creating_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'labels'
            labels = ReadOnlyLabels(root)
            self.assertEqual(labels.views(), [])
            self.assertIsNone(labels.find('atcoder', 'missing_a'))
            self.assertFalse(root.exists())

    def test_only_current_checkout_config_is_loaded(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'synthetic-inherited-key',
                                      'OPENAI_BASE_URL': 'https://wrong.invalid/v1'}), \
             patch('dotenv.dotenv_values', return_value={'OPENAI_BASE_URL': BASE_URL,
                                                        'OPENAI_MODEL': MODEL,
                                                        'OPENAI_API_KEY': 'synthetic-local-only'}) as reader:
            cfg = load_web_config()
        reader.assert_called_once_with(ROOT/'experiments/tags/ACM_Forever_Chinese_Tags_V0.3/.env')
        self.assertEqual(cfg.base_url, BASE_URL)
        self.assertEqual(cfg.model, MODEL)
        self.assertEqual(cfg.api_key, 'synthetic-local-only')

    def test_missing_local_key_does_not_use_inherited_key(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'synthetic-inherited-key'}), \
             patch('dotenv.dotenv_values', return_value={'OPENAI_BASE_URL': BASE_URL,
                                                        'OPENAI_MODEL': MODEL,
                                                        'OPENAI_API_KEY': ''}), \
             self.assertRaises(ValueError):
            load_web_config()
