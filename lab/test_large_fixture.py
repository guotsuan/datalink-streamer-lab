import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import large_fixture as large

class LargeFixtureTests(unittest.TestCase):
    def test_layout(self):
        self.assertEqual(len(large.header()), 2880)
        self.assertEqual(large.SIZE, 1_000_000_005_120)
        self.assertEqual(large.SIZE % 2880, 0)
        self.assertIn(b'NAXIS1  =              1000000', large.header())
        self.assertIn(b'NAXIS2  =              1000000', large.header())

    def test_exclusive_sparse_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'sample.fits'
            with patch.object(large, 'PATH', path), patch.object(large, 'SIZE', 8640):
                self.assertEqual(large.create()['bytes'], 8640)
                self.assertEqual(path.read_bytes(), large.header() + bytes(5760))
                before = path.stat().st_mtime_ns
                large.create()
                self.assertEqual(path.stat().st_mtime_ns, before)
                with path.open('r+b') as f: f.write(b'X')
                with self.assertRaises(RuntimeError): large.create()

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / 'real'
            target.touch()
            path = root / 'sample.fits'
            path.symlink_to(target)
            with patch.object(large, 'PATH', path):
                with self.assertRaises(RuntimeError): large.create()

if __name__ == '__main__': unittest.main()
