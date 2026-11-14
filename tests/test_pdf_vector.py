import json
import tempfile
import unittest
from pathlib import Path

import fitz
from pdf_vector import analyze_pdf_vector, format_analysis_summary


class LocalPdfVectorTests(unittest.TestCase):
    def test_extracts_vector_text_and_dimensions_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf_path = Path(folder) / "sample_cad.pdf"
            doc = fitz.open()
            page = doc.new_page(width=600, height=400)
            page.insert_text((60, 60), "PLATE 150 mm")
            page.draw_rect(fitz.Rect(80, 100, 230, 170), color=(0, 0, 0))
            page.draw_circle((300, 140), 25, color=(0, 0, 0))
            doc.save(pdf_path)
            doc.close()

            report = analyze_pdf_vector(pdf_path)
            self.assertEqual(report["page_count"], 1)
            self.assertGreaterEqual(report["summary"]["total_vector_paths"], 2)
            self.assertIn("150", report["pages"][0]["dimension_candidates"])
            self.assertTrue(report["safety"]["automatic_3d_inference"] is False)
            self.assertIn("PHÂN TÍCH PDF CỤC BỘ", format_analysis_summary(report))


if __name__ == "__main__":
    unittest.main()
