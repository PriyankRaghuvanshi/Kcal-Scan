import unittest
from unittest.mock import Mock, patch

import main as main_mod
from fastapi import HTTPException


class BarcodeLookupTests(unittest.TestCase):
    def test_openfoodfacts_lookup_retries_across_bases(self):
        failing = Mock(status_code=503, text='busy')
        success = Mock(status_code=200)
        success.json.return_value = {
            'status': 1,
            'product': {
                'product_name': 'Test Bar',
                'brands': 'Demo',
                'nutriments': {
                    'energy-kcal_100g': 420,
                    'proteins_100g': 25,
                    'carbohydrates_100g': 40,
                    'fat_100g': 12,
                },
            },
        }
        with patch('main.requests.get', side_effect=[failing, success]) as mocked_get:
            out = main_mod.openfoodfacts_lookup('1234567890123')
        self.assertEqual(out['name'], 'Test Bar')
        self.assertEqual(mocked_get.call_count, 2)

    def test_openfoodfacts_lookup_returns_503_when_all_upstreams_fail(self):
        failing = Mock(status_code=503, text='busy')

        def _always_fail(*_a, **_k):
            return failing

        with patch('main.requests.get', side_effect=_always_fail):
            with self.assertRaises(HTTPException) as ctx:
                main_mod.openfoodfacts_lookup('1234567890123')
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual((ctx.exception.detail or {}).get('error'), 'barcode_lookup_temporarily_unavailable')

    def test_openfoodfacts_lookup_returns_404_when_product_not_found(self):
        missing = Mock(status_code=200)
        missing.json.return_value = {
            'status': 0,
            'status_verbose': 'no code or invalid code',
        }
        with patch('main.requests.get', return_value=missing):
            with self.assertRaises(HTTPException) as ctx:
                main_mod.openfoodfacts_lookup('0000000000000')
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual((ctx.exception.detail or {}).get('error'), 'Barcode not found')

    def test_openfoodfacts_lookup_uses_macro_calorie_fallback(self):
        success = Mock(status_code=200)
        success.json.return_value = {
            'status': 1,
            'product': {
                'product_name': 'Macro Only Bar',
                'brands': 'Demo',
                'nutriments': {
                    'proteins_100g': 20,
                    'carbohydrates_100g': 30,
                    'fat_100g': 10,
                },
            },
        }
        with patch('main.requests.get', return_value=success):
            out = main_mod.openfoodfacts_lookup('1234567890123')
        self.assertEqual(out['name'], 'Macro Only Bar')
        self.assertEqual(out['kcal_per_100g'], 290.0)


if __name__ == '__main__':
    unittest.main()
