"""Offline tests for the bounded streaming benchmark."""
import contextlib
import importlib.util
import io
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('download_large', Path(__file__).parent / 'static/download_large.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Response(io.BytesIO):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}

class BenchmarkTests(unittest.TestCase):
    def run_client(self, corrupt=False, baseline_failure=False, default_size=False, checksum_failure=False):
        size = 1048576
        header = ('SIMPLE  =                    T'.ljust(80)+'END'.ljust(80)).ljust(2880).encode()
        body = header + bytes(size-2880)
        if corrupt: body = body[:-1]+b'x'
        responses = [Response(b''), Response(json.dumps({'bytes':1000000005120, 'did':'lab.test:large-1tb.fits'}).encode()),
            Response(b'<VOTABLE xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE ID="product-streamer"><PARAM name="accessURL" value="http://64.176.188.89:18080/streamer/v1/data/product"/></RESOURCE></VOTABLE>'),
            Response(body,206,{'Content-Length':str(1000000000 if default_size else size),'Content-Range':f'bytes 0-{(1000000000 if default_size else size)-1}/1000000005120'})]
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory)/'speed.json'
            argv = ['download_large.py','--report',str(report)] + ([] if default_size else ['--mib','1'])
            reference = {'sha256':'0'*64 if checksum_failure else hashlib.sha256(body).hexdigest(),'bytes':size,'method':'mock source'}
            with patch.object(module.sys,'argv',argv), patch.object(module.getpass,'getpass',return_value='test-only'), patch.object(module,'source_sha256',return_value=reference), patch.object(module,'iperf_baseline',return_value={'Mbit_s':100,'MiB_s':11.92}) as baseline, patch.object(module.request,'build_opener') as opener, contextlib.redirect_stdout(io.StringIO()):
                opener.return_value.open.side_effect = responses
                if baseline_failure:
                    baseline.side_effect = RuntimeError('baseline failed')
                    with self.assertRaisesRegex(RuntimeError,'baseline failed'): module.main()
                    self.assertEqual(opener.return_value.open.call_count,3)
                elif default_size:
                    with self.assertRaisesRegex(RuntimeError,'Incomplete transfer'): module.main()
                    self.assertEqual(opener.return_value.open.call_args.args[0].get_header('Range'), 'bytes=0-999999999')
                elif checksum_failure:
                    with self.assertRaisesRegex(RuntimeError,'SHA-256 mismatch'): module.main()
                elif corrupt:
                    with self.assertRaisesRegex(RuntimeError,'Nonzero'): module.main()
                else: module.main()
            return json.loads(report.read_text())

    def test_complete(self):
        result = self.run_client()
        self.assertTrue(result['complete'])
        self.assertTrue(result['sample_header_and_zero_data_check'])
        self.assertEqual(result['bytes'],1048576)
        self.assertEqual(result['iperf']['Mbit_s'],100)
        self.assertIsNotNone(result['download_to_iperf_percent'])
        self.assertTrue(result['sha256_matches'])

    def test_default_one_decimal_gb(self):
        result = self.run_client(default_size=True)
        self.assertFalse(result['complete'])
        self.assertEqual(result['expected'],1000000000)

    def test_corrupt_not_complete(self):
        result = self.run_client(corrupt=True)
        self.assertFalse(result['complete'])
        self.assertFalse(result['sample_header_and_zero_data_check'])

    def test_failed_baseline_stops_download(self):
        result = self.run_client(baseline_failure=True)
        self.assertEqual(result['iperf']['status'],'failed')
        self.assertEqual(result['download']['status'],'not_started')

    def test_checksum_mismatch_is_failure(self):
        result = self.run_client(checksum_failure=True)
        self.assertFalse(result['complete'])
        self.assertFalse(result['sha256_matches'])

if __name__ == '__main__': unittest.main()
