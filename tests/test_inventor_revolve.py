import unittest
from inventor_bridge import InventorBridgeError
from inventor_revolve import validate_revolve


class RevolveValidationTests(unittest.TestCase):
    def command(self):
        return {
            "op": "create_revolve", "component_id": "SHAFT", "unit": "mm",
            "plane": "XY", "loops": [{"type": "polyline", "points": [[10,0],[10,50],[15,50],[15,0]]}],
            "axis_points": [[0,0],[0,100]], "operation": "join", "full": True
        }

    def test_valid_full_revolve(self):
        cfg = validate_revolve(self.command())
        self.assertEqual(cfg["angle_deg"], 360.0)
        self.assertEqual(cfg["operation"], "join")

    def test_partial_revolve(self):
        cmd = self.command()
        cmd.update({"full": False, "angle_deg": 180})
        self.assertEqual(validate_revolve(cmd)["angle_deg"], 180)

    def test_rejects_zero_axis(self):
        cmd = self.command()
        cmd["axis_points"] = [[0,0],[0,0]]
        with self.assertRaises(InventorBridgeError):
            validate_revolve(cmd)

    def test_rejects_missing_units(self):
        cmd = self.command()
        cmd["unit"] = "pt"
        with self.assertRaises(InventorBridgeError):
            validate_revolve(cmd)

    def test_rejects_open_invalid_loop(self):
        cmd = self.command()
        cmd["loops"][0]["points"] = [[0,0],[1,0],[2,0]]
        with self.assertRaises(InventorBridgeError):
            validate_revolve(cmd)


if __name__ == "__main__":
    unittest.main()
