import unittest
from inventor_bridge import InventorBridgeError
from inventor_v09_features import (
    validate_spline_profile, validate_sweep, validate_loft,
    validate_shell, validate_mirror, validate_advanced_part
)


class V09FeatureValidationTests(unittest.TestCase):
    def test_closed_spline_profile(self):
        command = {
            "op": "create_spline_profile_extrude", "unit": "mm", "plane": "XY",
            "loops": [{"type": "spline", "control_points": [[0,0],[10,0],[10,10],[0,10],[0,0]]}],
            "distance": 5, "operation": "new_body"
        }
        self.assertEqual(validate_spline_profile(command)["distance"], 5)

    def test_open_spline_is_rejected(self):
        command = {
            "op": "create_spline_profile_extrude", "unit": "mm", "plane": "XY",
            "loops": [{"type": "spline", "control_points": [[0,0],[10,0],[10,10],[0,10]]}],
            "distance": 5
        }
        with self.assertRaises(InventorBridgeError):
            validate_spline_profile(command)

    def test_sweep_requires_named_profile_and_path(self):
        cfg = validate_sweep({
            "op": "create_sweep", "unit": "mm",
            "profile_sketch_name": "Section", "path_sketch_name": "Path",
            "path_curve_type": "arc", "path_curve_index": 1, "operation": "new_body"
        })
        self.assertEqual(cfg["path_curve_type"], "arc")

    def test_loft_requires_two_ordered_sections(self):
        cfg = validate_loft({
            "op": "create_loft", "unit": "mm",
            "section_sketch_names": ["Section_A", "Section_B"], "operation": "new_body"
        })
        self.assertEqual(len(cfg["section_sketch_names"]), 2)

    def test_shell_explicit_thickness(self):
        cfg = validate_shell({
            "op": "create_shell", "unit": "mm", "thickness_mm": 2,
            "direction": "inside", "remove_face_indices": [1, 2]
        })
        self.assertEqual(cfg["thickness_mm"], 2)

    def test_mirror_requires_existing_feature_names(self):
        cfg = validate_mirror({
            "op": "create_mirror", "unit": "mm",
            "feature_names": ["Extrusion1"], "work_plane_index": 3
        })
        self.assertEqual(cfg["work_plane_index"], 3)

    def test_dispatch_validator(self):
        command = {
            "op": "create_shell", "unit": "mm", "thickness_mm": 1
        }
        self.assertEqual(validate_advanced_part(command)["thickness_mm"], 1)


if __name__ == "__main__":
    unittest.main()
