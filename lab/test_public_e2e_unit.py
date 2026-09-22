"""Offline regression checks for the standalone public test client."""
from email.message import Message
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

from test_public_e2e import DEFAULT_BASE, LabTest, NoRedirect, Response, digest


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="datalink-e2e-unit-")
        self.addCleanup(self.temp.cleanup)
        self.lab = LabTest(DEFAULT_BASE, Path(self.temp.name), 2)
        (self.lab.directory / "downloads").mkdir()

    def response(self, content, code=200, **headers):
        h = Message()
        for name, value in headers.items():
            h[name.replace("_", "-")] = str(value)
        return Response(code, h, content)

    def test_fixture_oracle(self):
        content = self.lab.expected["image.fits"]
        self.assertEqual(len(content), 5760)
        self.assertEqual(digest(content), "960bdff5cafd024bce6d14e10c11b9dee8d35efc0b328dfc6080080628c18600")
        self.assertEqual(len(self.lab.expected["range.bin"]), 1048576)

    def test_correct_content(self):
        content = self.lab.expected["image.fits"]
        evidence = self.lab.verify_file(self.response(content, Content_Length=len(content)), "image.fits")
        self.assertEqual(evidence["bytes"], 5760)

    def test_corrupt_content_fails(self):
        content = self.lab.expected["image.fits"]
        with self.assertRaisesRegex(AssertionError, "SHA-256"):
            self.lab.verify_file(self.response(b"x" + content[1:]), "image.fits")

    def test_wrong_content_length_fails(self):
        with self.assertRaisesRegex(AssertionError, "Content-Length"):
            self.lab.verify_file(self.response(self.lab.expected["image.fits"], Content_Length=1), "image.fits")

    def test_foreign_origin_never_requested(self):
        with self.assertRaisesRegex(AssertionError, "outside configured origin"):
            self.lab.request("GET", "http://localhost:18080/mock/token")
        self.assertFalse(self.lab.requests)

    def test_redirects_disabled(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.invalid"))

    def test_tar_integrity(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w") as archive:
            for name in ["image.fits", "readme.txt", "metadata.json"]:
                content = self.lab.expected[name]
                entry = tarfile.TarInfo(name)
                entry.size = len(content)
                archive.addfile(entry, io.BytesIO(content))
        self.lab.stream = lambda *a, **kw: self.response(data.getvalue(), Content_Type="application/x-tar")
        evidence = self.lab.archive()
        self.assertEqual(len(evidence["members"]), 3)

    def test_unexpected_tar_member_fails_without_extraction(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w") as archive:
            entry = tarfile.TarInfo("../outside")
            archive.addfile(entry, io.BytesIO(b""))
        self.lab.stream = lambda *a, **kw: self.response(data.getvalue(), Content_Type="application/x-tar")
        with self.assertRaisesRegex(AssertionError, "Unexpected TAR"):
            self.lab.archive()
        self.assertFalse((self.lab.directory / "downloads/dataset.tar").exists())

    def test_diagnostics_remain_warnings(self):
        self.lab.standard_findings = [{"mime": "application/xml", "standard_id": []}]
        self.assertFalse(self.lab.record("MIME", self.lab.mime_check, diagnostic=True))
        self.assertEqual(self.lab.results[-1]["status"], "WARN")


if __name__ == "__main__":
    unittest.main()
