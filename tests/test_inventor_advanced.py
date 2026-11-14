import unittest
from inventor_bridge import InventorBridgeError
from inventor_advanced import validate_advanced_profile


class AdvancedProfileValidationTests(unittest.TestCase):
    def valid(self):
        return {"op":"create_profile_extrude","unit":"mm","plane":"YZ",
                "loops":[{"type":"polyline","points":[[0,0],[100,0],[80,40],[0,40]]},
                         {"type":"circle","center_x":30,"center_y":20,"radius":5}],
                "distance":8,"operation":"new_body","direction":"positive"}

    def test_valid_multi_loop_profile_on_yz_plane(self):
        result=validate_advanced_profile(self.valid())
        self.assertEqual(result["plane"],"YZ")
        self.assertEqual(len(result["loops"]),2)
        self.assertEqual(result["distance"],8)

    def test_rejects_missing_units(self):
        c=self.valid(); c.pop("unit")
        with self.assertRaises(InventorBridgeError): validate_advanced_profile(c)

    def test_rejects_degenerate_polyline(self):
        c=self.valid(); c["loops"][0]["points"]=[[0,0],[1,1],[2,2]]
        with self.assertRaises(InventorBridgeError): validate_advanced_profile(c)

    def test_rejects_invalid_plane(self):
        c=self.valid(); c["plane"]="AB"
        with self.assertRaises(InventorBridgeError): validate_advanced_profile(c)

    def test_rejects_nonpositive_distance(self):
        c=self.valid(); c["distance"]=0
        with self.assertRaises(InventorBridgeError): validate_advanced_profile(c)


if __name__ == "__main__":
    unittest.main()
