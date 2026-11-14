import unittest

from inventor_bridge import InventorBridgeError
from inventor_geometry import validate_rectangle_command, validate_circle_command, validate_profile_command


class RectangleCommandValidationTests(unittest.TestCase):
    def valid_command(self):
        return {
            "op": "create_rectangle_extrude",
            "length": 150,
            "width": 70,
            "thickness": 8,
            "unit": "mm",
            "origin_x": 0,
            "origin_y": 0,
        }

    def test_valid_rectangle_is_normalized(self):
        result = validate_rectangle_command(self.valid_command())
        self.assertEqual(result["length"], 150)
        self.assertEqual(result["width"], 70)
        self.assertEqual(result["thickness"], 8)
        self.assertEqual(result["unit"], "mm")
        self.assertEqual(result["direction"], "positive")
        self.assertEqual(result["parameter_names"]["length"], "Length")

    def test_rejects_missing_explicit_units(self):
        command = self.valid_command()
        command.pop("unit")
        with self.assertRaises(InventorBridgeError):
            validate_rectangle_command(command)

    def test_rejects_zero_or_negative_dimensions(self):
        for key in ("length", "width", "thickness"):
            command = self.valid_command()
            command[key] = 0
            with self.subTest(key=key):
                with self.assertRaises(InventorBridgeError):
                    validate_rectangle_command(command)

    def test_rejects_boolean_as_numeric_dimension(self):
        command = self.valid_command()
        command["length"] = True
        with self.assertRaises(InventorBridgeError):
            validate_rectangle_command(command)

    def test_rejects_unknown_extrude_direction(self):
        command = self.valid_command()
        command["direction"] = "both"
        with self.assertRaises(InventorBridgeError):
            validate_rectangle_command(command)

    def test_rejects_invalid_parameter_identifier(self):
        command = self.valid_command()
        command["parameter_names"] = {"length": "Length with spaces"}
        with self.assertRaises(InventorBridgeError):
            validate_rectangle_command(command)

    def test_rejects_duplicate_parameter_names(self):
        command = self.valid_command()
        command["parameter_names"] = {
            "length": "Size",
            "width": "Size",
            "thickness": "Depth",
        }
        with self.assertRaises(InventorBridgeError):
            validate_rectangle_command(command)




class ProfileCutoutValidationTests(unittest.TestCase):
    def valid_command(self):
        return {
            "op": "create_profile_extrude",
            "unit": "mm",
            "thickness": 8,
            "direction": "positive",
            "points": [
                {"x": 0, "y": 0},
                {"x": 100, "y": 0},
                {"x": 100, "y": 60},
                {"x": 0, "y": 60},
            ],
            "holes": [],
            "cutouts": [[
                {"x": 40, "y": 20},
                {"x": 60, "y": 20},
                {"x": 60, "y": 40},
                {"x": 40, "y": 40},
            ]],
        }

    def test_accepts_inner_polygon_cutout(self):
        result = validate_profile_command(self.valid_command())
        self.assertEqual(len(result["cutouts"]), 1)
        self.assertEqual(len(result["cutouts"][0]), 4)

    def test_rejects_cutout_outside_outer_profile(self):
        command = self.valid_command()
        command["cutouts"] = [[
            {"x": 90, "y": 20},
            {"x": 110, "y": 20},
            {"x": 110, "y": 40},
            {"x": 90, "y": 40},
        ]]
        with self.assertRaises(InventorBridgeError):
            validate_profile_command(command)

    def test_rejects_overlapping_cutouts(self):
        command = self.valid_command()
        command["cutouts"].append([
            {"x": 50, "y": 30},
            {"x": 70, "y": 30},
            {"x": 70, "y": 50},
            {"x": 50, "y": 50},
        ])
        with self.assertRaises(InventorBridgeError):
            validate_profile_command(command)


class CircleCommandValidationTests(unittest.TestCase):
    def valid_command(self):
        return {
            "op": "create_circle_extrude",
            "diameter": 20,
            "thickness": 8,
            "center_x": 25,
            "center_y": 30,
            "unit": "mm",
            "operation": "cut",
            "direction": "positive",
        }

    def test_valid_circle_cut_is_normalized(self):
        result = validate_circle_command(self.valid_command())
        self.assertEqual(result["diameter"], 20)
        self.assertEqual(result["thickness"], 8)
        self.assertEqual(result["operation"], "cut")
        self.assertEqual(result["parameter_names"]["diameter"], "Diameter")

    def test_rejects_circle_without_explicit_units(self):
        command = self.valid_command()
        command.pop("unit")
        with self.assertRaises(InventorBridgeError):
            validate_circle_command(command)

    def test_rejects_nonpositive_diameter(self):
        command = self.valid_command()
        command["diameter"] = -1
        with self.assertRaises(InventorBridgeError):
            validate_circle_command(command)

    def test_rejects_invalid_circle_operation(self):
        command = self.valid_command()
        command["operation"] = "blend"
        with self.assertRaises(InventorBridgeError):
            validate_circle_command(command)




class ProfileCommandValidationTests(unittest.TestCase):
    def valid_command(self):
        return {
            "op": "create_profile_extrude",
            "unit": "mm",
            "thickness": 8,
            "direction": "positive",
            "points": [
                {"x": 0, "y": 0},
                {"x": 100, "y": 0},
                {"x": 100, "y": 50},
                {"x": 0, "y": 50},
            ],
            "holes": [
                {"center_x": 25, "center_y": 25, "diameter": 10},
                {"center_x": 75, "center_y": 25, "diameter": 10},
            ],
        }

    def test_valid_profile_with_round_holes(self):
        result = validate_profile_command(self.valid_command())
        self.assertEqual(len(result["points"]), 4)
        self.assertEqual(len(result["holes"]), 2)
        self.assertEqual(result["thickness"], 8)
        self.assertEqual(result["holes"][0]["diameter"], 10)

    def test_rejects_self_intersecting_profile(self):
        command = self.valid_command()
        command["holes"] = []
        command["points"] = [
            {"x": 0, "y": 0},
            {"x": 100, "y": 50},
            {"x": 0, "y": 50},
            {"x": 100, "y": 0},
        ]
        with self.assertRaises(InventorBridgeError):
            validate_profile_command(command)

    def test_rejects_hole_outside_profile(self):
        command = self.valid_command()
        command["holes"] = [{"center_x": 150, "center_y": 25, "diameter": 10}]
        with self.assertRaises(InventorBridgeError):
            validate_profile_command(command)

    def test_rejects_hole_intersecting_outer_edge(self):
        command = self.valid_command()
        command["holes"] = [{"center_x": 5, "center_y": 25, "diameter": 20}]
        with self.assertRaises(InventorBridgeError):
            validate_profile_command(command)

    def test_rejects_overlapping_holes(self):
        command = self.valid_command()
        command["holes"] = [
            {"center_x": 40, "center_y": 25, "diameter": 20},
            {"center_x": 50, "center_y": 25, "diameter": 20},
        ]
        with self.assertRaises(InventorBridgeError):
            validate_profile_command(command)

    def test_rejects_missing_units(self):
        command = self.valid_command()
        command.pop("unit")
        with self.assertRaises(InventorBridgeError):
            validate_profile_command(command)


if __name__ == "__main__":
    unittest.main()
