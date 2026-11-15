import unittest
from inventor_bridge import InventorBridgeError
from pdf_feature_planner import list_closed_profile_candidates, build_pdf_feature_plan


class PdfFeaturePlannerTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "source_file": "shaft-bracket.pdf",
            "pages": [{
                "page_size_pt": [600, 800],
                "vector_paths": [{
                    "closed": True,
                    "bbox_pt": [10, 10, 110, 60],
                    "items": [
                        {"type": "l", "data": [[10,10],[110,10]]},
                        {"type": "l", "data": [[110,10],[110,60]]},
                        {"type": "l", "data": [[110,60],[10,60]]},
                        {"type": "l", "data": [[10,60],[10,10]]}
                    ]
                }]
            }]
        }

    def test_closed_vector_candidate_is_listed(self):
        candidates = list_closed_profile_candidates(self.report, 1)
        self.assertEqual(candidates[0]["path_index"], 1)

    def test_builds_extrude_plan_with_explicit_scale_and_depth(self):
        plan = build_pdf_feature_plan(
            self.report, 1, [1], 0.2, 12, "PART_01",
            plane="XY", operation="new_body"
        )
        command = plan["commands"][0]
        self.assertEqual(command["distance"], 12)
        self.assertEqual(command["loops"][0]["points"][1][0], 20)
        self.assertFalse(plan["automatic_inference"]["scale_from_pdf"])
        self.assertEqual(plan["calibration"]["mm_per_pt"], 0.2)

    def test_rejects_missing_scale(self):
        with self.assertRaises(InventorBridgeError):
            build_pdf_feature_plan(self.report, 1, [1], 0, 12, "PART_01")

    def test_rejects_non_line_closed_path(self):
        self.report["pages"][0]["vector_paths"][0]["items"][0]["type"] = "c"
        with self.assertRaises(InventorBridgeError):
            build_pdf_feature_plan(self.report, 1, [1], 0.2, 12, "PART_01")


if __name__ == "__main__":
    unittest.main()
