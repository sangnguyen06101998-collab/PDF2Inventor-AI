import unittest
import json
import os
import tempfile
from pathlib import Path

import fitz
from unittest.mock import patch

from pdf_ai import (
    PdfAIError,
    analysis_schema,
    build_command_document,
    format_analysis_report,
    _extract_output_text,
    analyze_pdf,
    _dpapi_crypt,
    verify_scale_references,
    validate_command_dimensions,
    derive_profile_from_vectors,
)


class WindowsDpapiTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows DPAPI is only available on Windows.")
    def test_windows_dpapi_round_trip(self):
        original = b"PDF2Inventor test API key"
        protected = _dpapi_crypt(original)
        self.assertNotEqual(protected, original)
        restored = _dpapi_crypt(protected, decrypt=True)
        self.assertEqual(restored, original)


class PdfAiSchemaTests(unittest.TestCase):
    def test_schema_requires_analysis_and_cad_fields(self):
        schema = analysis_schema()
        self.assertIn("cad_command", schema["required"])
        self.assertIn("dimensions_detected", schema["required"])
        self.assertFalse(schema["additionalProperties"])

    def test_rectangle_command_is_wrapped_for_current_project(self):
        analysis = {
            "cad_command": {
                "op": "create_rectangle_extrude",
                "component_id": "WRONG_ID_FROM_MODEL",
                "length": 120,
                "width": 80,
                "thickness": 6,
                "origin_x": 0,
                "origin_y": 0,
                "diameter": None,
                "center_x": None,
                "center_y": None,
                "unit": "mm",
                "operation": "new_body",
                "direction": "positive",
                "reason": "Plate part",
            },
            "questions": [],
            "warnings": ["Check the drawing before applying."],
            "confidence": "high",
            "scale_status": "verified",
            "scale_verification": {"verified": True, "mm_per_pt": 1.0},
            "overall_length_mm": 120,
            "overall_width_mm": 80,
            "overall_height_mm": 6,
        }
        result = build_command_document(analysis, "PROJECT_X", "PART_X")
        self.assertEqual(result["project_id"], "PROJECT_X")
        self.assertEqual(result["commands"][0]["component_id"], "PART_X")
        self.assertEqual(result["commands"][0]["length"], 120)
        self.assertEqual(result["commands"][0]["unit"], "mm")
        self.assertEqual(result["warnings"], ["Check the drawing before applying."])

    def test_profile_extrude_command_is_validated_and_wrapped(self):
        analysis = {
            "cad_command": {
                "op": "create_profile_extrude",
                "component_id": "WRONG_ID",
                "thickness": 8,
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 100, "y": 0},
                    {"x": 100, "y": 60},
                    {"x": 0, "y": 60},
                ],
                "holes": [{"center_x": 20, "center_y": 20, "diameter": 10}],
                "unit": "mm",
                "operation": "new_body",
                "direction": "positive",
                "profile_vector_path_id": 12,
                "hole_vector_path_ids": [13],
                "reason": "Flat bracket profile",
            },
            "questions": [],
            "warnings": [],
            "confidence": "high",
            "scale_status": "verified",
            "scale_verification": {"verified": True, "mm_per_pt": 2.0},
            "overall_length_mm": 100,
            "overall_width_mm": 60,
            "overall_height_mm": 8,
            "dimensions_detected": [{"label": "Hole diameter", "value": 10, "unit": "mm", "view": "Front", "page": 1, "evidence": "Ø10", "confidence": "high"}],
        }
        result = build_command_document(analysis, "PROJECT_Y", "PART_Y")
        self.assertEqual(result["commands"][0]["component_id"], "PART_Y")
        self.assertEqual(result["commands"][0]["op"], "create_profile_extrude")
        self.assertEqual(len(result["commands"][0]["points"]), 4)
        self.assertEqual(len(result["commands"][0]["holes"]), 1)

    def test_rejects_cad_command_with_missing_dimension(self):
        analysis = {
            "cad_command": {
                "op": "create_rectangle_extrude",
                "length": None,
                "width": 80,
                "thickness": 6,
                "unit": "mm",
            }
        }
        with self.assertRaises(PdfAIError):
            build_command_document(analysis, "PROJECT_X", "PART_X")

    def test_no_command_does_not_create_empty_geometry(self):
        with self.assertRaises(PdfAIError):
            build_command_document(
                {"cad_command": None, "questions": ["What is the thickness?"]},
                "PROJECT_X",
                "PART_X",
            )

    def test_extracts_responses_output_text(self):
        response = {"output_text": '{"ok":true}'}
        self.assertEqual(_extract_output_text(response), '{"ok":true}')

    def test_extracts_message_content_fallback(self):
        response = {
            "output": [{
                "content": [{"type": "output_text", "text": '{"ok":true}'}]
            }]
        }
        self.assertEqual(_extract_output_text(response), '{"ok":true}')

    def test_schema_includes_polygon_profile_and_hole_data(self):
        schema = analysis_schema()
        command = schema["properties"]["cad_command"]["anyOf"][0]
        self.assertIn("points", command["properties"])
        self.assertIn("holes", command["properties"])
        self.assertIn("create_profile_extrude", command["properties"]["op"]["enum"])

    def test_analyze_pdf_sends_pdf_file_as_vision_input(self):
        analysis_json = json.dumps({
            "drawing_type": "single_part",
            "drawing_title": "Plate",
            "part_name": "Plate",
            "units": "mm",
            "overall_length_mm": 100,
            "overall_width_mm": 50,
            "overall_height_mm": 8,
            "views_detected": ["Front"],
            "dimensions_detected": [],
            "feature_summary": ["Flat rectangular plate"],
            "manufacturing_notes": [],
            "confidence": "high",
            "cad_command": None,
            "questions": ["Confirm whether holes are required."],
            "warnings": [],
        })
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({"output_text": analysis_json}).encode("utf-8")

        def fake_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse()

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "drawing.pdf"
            document = fitz.open()
            page = document.new_page(width=300, height=200)
            page.draw_rect(fitz.Rect(30, 30, 150, 90), color=(0, 0, 0), width=0.5)
            page.draw_line(fitz.Point(30, 110), fitz.Point(150, 110), color=(0, 0, 0), width=0.25)
            page.draw_line(fitz.Point(30, 120), fitz.Point(30, 160), color=(0, 0, 0), width=0.25)
            page.insert_text((60, 25), "120 mm", fontsize=8)
            page.insert_text((10, 80), "40 mm", fontsize=8)
            document.save(path)
            document.close()
            with patch("pdf_ai.urllib.request.urlopen", side_effect=fake_urlopen):
                result = analyze_pdf(
                    pdf_path=str(path),
                    api_key="sk-test",
                    model="gpt-4.1",
                    detail="high",
                    project_id="PROJECT_1",
                    component_id="PART_1",
                    part_name="Test plate",
                    document_path="C:/CAD/Test.ipt",
                )

        self.assertEqual(result["part_name"], "Plate")
        self.assertFalse(captured["body"]["store"])
        file_item = captured["body"]["input"][0]["content"][0]
        self.assertEqual(file_item["type"], "input_file")
        self.assertEqual(file_item["filename"], "drawing.pdf")
        self.assertEqual(file_item["detail"], "high")
        self.assertTrue(file_item["file_data"].startswith("data:application/pdf;base64,"))
        self.assertGreater(captured["timeout"], 0)

    def test_refusal_is_reported(self):
        response = {
            "output": [{
                "content": [{"type": "refusal", "refusal": "cannot process"}]
            }]
        }
        with self.assertRaises(PdfAIError):
            _extract_output_text(response)




class VectorScaleVerificationTests(unittest.TestCase):
    def vector_report(self):
        return {
            "native_vector_pdf": True,
            "page_details": [{
                "page": 1,
                "dimension_text_candidates": ["200 mm", "100 mm", "150 mm"],
                "paths": [
                    {
                        "id": 10,
                        "segments": [["L", 0, 0, 100, 0]],
                    },
                    {
                        "id": 11,
                        "segments": [["L", 0, 0, 0, 50]],
                    },
                    {
                        "id": 12,
                        "closed": True,
                        "bbox_pt": [10, 10, 110, 60],
                        "segments": [
                            ["L", 10, 10, 110, 10],
                            ["L", 110, 10, 110, 60],
                            ["L", 110, 60, 10, 60],
                            ["L", 10, 60, 10, 10],
                        ],
                    },
                    {
                        "id": 13,
                        "closed": True,
                        "has_circle_or_arc_candidate": True,
                        "bbox_pt": [30, 25, 40, 35],
                        "segments": [["C", 30, 30, 32, 25, 38, 25, 40, 30]],
                    },
                ],
            }],
        }

    def test_scale_references_are_recomputed_from_vector_lines(self):
        report = self.vector_report()
        analysis = {
            "units": "mm",
            "geometry_view": "Front",
            "geometry_page": 1,
            "scale_references": [
                {
                    "dimension_text": "200",
                    "value_mm": 200,
                    "measured_length_pt": 100,
                    "mm_per_pt": 2,
                    "page": 1,
                    "vector_path_id": 10,
                    "segment_index": 0,
                    "axis": "x",
                    "view": "Front",
                    "confidence": "high",
                },
                {
                    "dimension_text": "100",
                    "value_mm": 100,
                    "measured_length_pt": 50,
                    "mm_per_pt": 2,
                    "page": 1,
                    "vector_path_id": 11,
                    "segment_index": 0,
                    "axis": "y",
                    "view": "Front",
                    "confidence": "high",
                },
            ],
        }
        result = verify_scale_references(report, analysis)
        self.assertTrue(result["verified"])
        self.assertEqual(result["mm_per_pt"], 2)
        self.assertEqual(len(result["references_checked"]), 2)

    def test_scale_conflict_fails_when_x_and_y_are_inconsistent(self):
        report = self.vector_report()
        analysis = {
            "units": "mm",
            "geometry_view": "Front",
            "geometry_page": 1,
            "scale_references": [
                {
                    "dimension_text": "200", "value_mm": 200, "measured_length_pt": 100,
                    "mm_per_pt": 2, "page": 1, "vector_path_id": 10, "segment_index": 0,
                    "axis": "x", "view": "Front", "confidence": "high",
                },
                {
                    "dimension_text": "150", "value_mm": 150, "measured_length_pt": 50,
                    "mm_per_pt": 3, "page": 1, "vector_path_id": 11, "segment_index": 0,
                    "axis": "y", "view": "Front", "confidence": "high",
                },
            ],
        }
        result = verify_scale_references(report, analysis)
        self.assertFalse(result["verified"])
        self.assertIn("sai khác", result["reason"])

    def test_vector_profile_and_circle_are_converted_to_mm(self):
        result = derive_profile_from_vectors(
            self.vector_report(),
            1,
            12,
            [13],
            2.0,
        )
        self.assertEqual(len(result["points"]), 4)
        self.assertEqual(result["points"], [
            {"x": 0.0, "y": 100.0},
            {"x": 200.0, "y": 100.0},
            {"x": 200.0, "y": 0.0},
            {"x": 0.0, "y": 0.0},
        ])
        self.assertEqual(result["holes"][0]["diameter"], 20.0)
        self.assertEqual(result["holes"][0]["center_x"], 50.0)
        self.assertEqual(result["holes"][0]["center_y"], 60.0)

    def test_vector_inner_polygon_becomes_an_exact_cutout(self):
        report = self.vector_report()
        report["page_details"][0]["paths"].append({
            "id": 14,
            "closed": True,
            "bbox_pt": [60, 30, 80, 40],
            "segments": [
                ["L", 60, 30, 80, 30],
                ["L", 80, 30, 80, 40],
                ["L", 80, 40, 60, 40],
                ["L", 60, 40, 60, 30],
            ],
        })
        result = derive_profile_from_vectors(report, 1, 12, [13], 2.0, [14])
        self.assertEqual(len(result["cutouts"]), 1)
        self.assertEqual(result["cutouts"][0], [
            {"x": 100.0, "y": 60.0},
            {"x": 140.0, "y": 60.0},
            {"x": 140.0, "y": 40.0},
            {"x": 100.0, "y": 40.0},
        ])

    def test_vector_curve_is_sampled_into_short_segments(self):
        report = self.vector_report()
        report["page_details"][0]["paths"].append({
            "id": 15,
            "closed": True,
            "bbox_pt": [10, 10, 100, 50],
            "segments": [
                ["L", 10, 10, 90, 10],
                ["C", 90, 10, 100, 10, 100, 50, 90, 50],
                ["L", 90, 50, 10, 50],
                ["L", 10, 50, 10, 10],
            ],
        })
        result = derive_profile_from_vectors(report, 1, 15, [], 1.0)
        self.assertGreater(len(result["points"]), 4)
        self.assertEqual(result["curves_approximated"], 1)

    def test_bounding_dimensions_must_match_drawing_values(self):
        analysis = {
            "overall_length_mm": 200,
            "overall_width_mm": 100,
            "overall_height_mm": 8,
            "dimensions_detected": [],
        }
        command = {
            "op": "create_profile_extrude",
            "points": [
                {"x": 0, "y": 0},
                {"x": 200, "y": 0},
                {"x": 200, "y": 100},
                {"x": 0, "y": 100},
            ],
            "thickness": 8,
            "holes": [],
        }
        self.assertEqual(validate_command_dimensions(analysis, command), [])
        command["thickness"] = 10
        self.assertTrue(validate_command_dimensions(analysis, command))


class PdfAiReportTests(unittest.TestCase):
    def test_report_contains_dimensions_and_questions(self):
        report = format_analysis_report({
            "drawing_title": "Bracket",
            "part_name": "Bracket",
            "drawing_type": "single_part",
            "units": "mm",
            "overall_length_mm": 100,
            "overall_width_mm": 50,
            "overall_height_mm": 8,
            "confidence": "high",
            "views_detected": ["Front view", "Side view"],
            "dimensions_detected": [{
                "label": "Length",
                "value": 100,
                "unit": "mm",
                "view": "Front",
                "evidence": "Dimension line marked 100",
                "confidence": "high",
            }],
            "feature_summary": ["Flat rectangular plate"],
            "manufacturing_notes": [],
            "questions": ["Confirm hole diameter."],
            "warnings": [],
            "cad_command": None,
        })
        self.assertIn("Bracket", report)
        self.assertIn("100 mm", report)
        self.assertIn("Confirm hole diameter", report)
        self.assertIn("Chưa tạo lệnh", report)


if __name__ == "__main__":
    unittest.main()
