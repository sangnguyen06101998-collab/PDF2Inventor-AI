import unittest
from inventor_bridge import InventorBridgeError
from inventor_holes import validate_hole_command


class HoleValidationTests(unittest.TestCase):
    def valid(self):
        return {"op":"create_hole","unit":"mm","plane":"XY","offset_mm":12,
                "diameter":8,"centers":[[20,20],[80,20]],"extent":"through_all"}
    def test_valid_multi_hole_command(self):
        c=validate_hole_command(self.valid())
        self.assertEqual(len(c["centers"]),2)
        self.assertEqual(c["offset_mm"],12)
    def test_rejects_missing_units(self):
        c=self.valid(); c.pop("unit")
        with self.assertRaises(InventorBridgeError): validate_hole_command(c)
    def test_rejects_nonpositive_diameter(self):
        c=self.valid(); c["diameter"]=0
        with self.assertRaises(InventorBridgeError): validate_hole_command(c)
    def test_requires_depth_for_blind_hole(self):
        c=self.valid(); c["extent"]="distance"
        with self.assertRaises(InventorBridgeError): validate_hole_command(c)


if __name__=="__main__": unittest.main()
