import os
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
from voicebridge import storage
from voicebridge.service import endpoint_url, session_config


class ConfigTests(unittest.TestCase):
    def test_model_is_encoded_and_endpoint_must_be_secure(self):
        result = endpoint_url({'endpoint': 'wss://example.org/realtime', 'model': 'model & variant'})
        self.assertEqual(parse_qs(urlsplit(result).query), {'model': ['model & variant']})
        for url in ['ws://example.org', 'wss://user:password@example.org']:
            with self.assertRaises(ValueError):
                endpoint_url({'endpoint': url})

    def test_user_key_overrides_environment(self):
        with patch.object(storage, 'read_secret', return_value='saved-credential'), patch.dict(os.environ, VOICEBRIDGE_API_KEY='environment-credential'):
            self.assertEqual(storage.load_key(), 'saved-credential')

    def test_languages_and_legacy_protocol(self):
        options = dict(storage.DEFAULTS, target='ja')
        voice = {'voice': 'Ethan', 'mode': None}
        self.assertEqual(session_config(options, voice)['output_modalities'], ['text', 'audio'])
        options.update(target='it', protocol='qwen35')
        config = session_config(options, voice)
        self.assertEqual(config['modalities'], ['text'])
        self.assertNotIn('output_modalities', config)
        self.assertEqual(config['translation']['language'], 'it')
        self.assertEqual(config['sample_rate'], 16000)


if __name__ == '__main__':
    unittest.main()
