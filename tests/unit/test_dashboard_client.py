import unittest

from tests.unit import _stubs  # noqa: F401
from libgrabsite.dashboard_client import Decayer


class DecayerTests(unittest.TestCase):
    def test_first_decay_returns_initial(self):
        self.assertAlmostEqual(Decayer(0.25, 1.5, 8).decay(), 0.25)

    def test_multiplies_each_call(self):
        d = Decayer(1, 2, 100)
        self.assertEqual([d.decay() for _ in range(4)], [1, 2, 4, 8])

    def test_capped_at_maximum(self):
        d = Decayer(1, 2, 5)
        self.assertEqual([d.decay() for _ in range(5)], [1, 2, 4, 5, 5])

    def test_reset_restarts_sequence(self):
        d = Decayer(1, 2, 100)
        for _ in range(3):
            d.decay()
        d.reset()
        self.assertEqual(d.decay(), 1)


if __name__ == "__main__":
    unittest.main()
