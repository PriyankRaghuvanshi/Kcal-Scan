import unittest

from upf_quick_logic import parse_upf_quick_model_output


class TestUpfQuickParse(unittest.TestCase):
    def test_parse_score(self):
        self.assertAlmostEqual(parse_upf_quick_model_output('{"ultra_processed_score": 7.2}'), 7.2)

    def test_clamps_high(self):
        self.assertAlmostEqual(parse_upf_quick_model_output('{"ultra_processed_score": 15}'), 10.0)

    def test_clamps_low(self):
        self.assertAlmostEqual(parse_upf_quick_model_output('{"ultra_processed_score": -3}'), 0.0)

    def test_missing_raises(self):
        with self.assertRaises(ValueError):
            parse_upf_quick_model_output("{}")


if __name__ == "__main__":
    unittest.main()
