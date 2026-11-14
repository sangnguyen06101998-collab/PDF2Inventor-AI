import json
import tempfile
import unittest
from pathlib import Path

import fitz

from pdf_vector import compact_vector_context, extract_pdf_vector_report


class PdfVectorExtractionTests(unittest.TestCase):
    def make_vector_pdf(self, folder):
        path = Path(folder) / "cad_export_test.pdf"
        document = fitz.open()
        page = document.new_page(width=300, height=200)
        page.draw_rect(fitz.Rect(40, 40, 160, 100), color=(0, 0, 0), width=0.5)
        page.draw_line(fitz.Point(40, 120), fitz.Point(160, 120), color=(0, 0, 0), width=0.25)
        page.draw_line(fitz.Point(40, 130), fitz.Point(40, 170), color=(0, 0, 0), width=0.25)
        page.insert_text((80, 30), "120 mm", fontsize=8)
        page.insert_text((20, 90), "60 mm", fontsize=8)
        document.save(path)
        document.close()
        return path

    def test_extracts_native_vector_paths_and_dimension_text(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_vector_pdf(folder)
            report = extract_pdf_vector_report(str(path))

        self.assertTrue(report["native_vector_pdf"])
        self.assertEqual(report["page_count"], 1)
        self.assertGreater(report["total_path_count"], 0)
        self.assertGreater(report["total_vector_segment_count"], 0)
        page = report["page_details"][0]
        self.assertGreater(page["vector_path_count"], 0)
        self.assertTrue(page["paths"])
        self.assertIn("120 mm", " ".join(page["dimension_text_candidates"]))

    def test_compact_vector_context_is_valid_json_and_keeps_path_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_vector_pdf(folder)
            report = extract_pdf_vector_report(str(path))
        compact = compact_vector_context(report)
        decoded = json.loads(compact)
        self.assertTrue(decoded["native_vector_pdf"])
        self.assertTrue(decoded["page_details"][0]["paths"])
        self.assertIn("id", decoded["page_details"][0]["paths"][0])

    def test_rejects_non_pdf_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "not_pdf.txt"
            path.write_text("not a PDF", encoding="utf-8")
            with self.assertRaises(ValueError):
                extract_pdf_vector_report(str(path))


if __name__ == "__main__":
    unittest.main()
