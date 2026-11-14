import unittest

from inventor_bridge import InventorBridgeError
from inventor_geometry import validate_rectangle_command, validate_circle_command


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


if __name__ == "__main__":
    unittest.main()
