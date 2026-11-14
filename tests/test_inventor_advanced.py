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

    def test_valid_closed_line_arc_profile(self):
        c=self.valid()
        c["loops"]=[{"type":"segments","segments":[
            {"type":"line","start":[0,0],"end":[40,0]},
            {"type":"arc","start":[40,0],"end":[0,0],"center":[20,0],"counterclockwise":True}
        ]}]
        result=validate_advanced_profile(c)
        self.assertEqual(result["loops"][0]["type"],"segments")

    def test_rejects_open_segment_profile(self):
        c=self.valid()
        c["loops"]=[{"type":"segments","segments":[
            {"type":"line","start":[0,0],"end":[40,0]},
            {"type":"line","start":[40,1],"end":[0,0]}
        ]}]
        with self.assertRaises(InventorBridgeError): validate_advanced_profile(c)

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
