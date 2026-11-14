import unittest
from inventor_bridge import InventorBridgeError
from inventor_patterns import validate_pattern


class PatternValidationTests(unittest.TestCase):
    def test_valid_circular_pattern(self):
        c={"op":"create_circular_pattern","unit":"mm","feature_names":["Hole1"],"axis_index":3,"count":6,"angle_deg":360}
        self.assertEqual(validate_pattern(c)["count"],6)

    def test_valid_rectangular_pattern(self):
        c={"op":"create_rectangular_pattern","unit":"mm","feature_names":["Rib1"],"axis_x_index":1,"axis_y_index":2,"count_x":3,"count_y":2,"spacing_x":40,"spacing_y":25}
        self.assertEqual(validate_pattern(c)["count_y"],2)

    def test_rejects_pattern_count_one(self):
        c={"op":"create_circular_pattern","unit":"mm","feature_names":["Hole1"],"count":1}
        with self.assertRaises(InventorBridgeError): validate_pattern(c)

    def test_rejects_missing_feature_names(self):
        c={"op":"create_circular_pattern","unit":"mm","feature_names":[],"count":3}
        with self.assertRaises(InventorBridgeError): validate_pattern(c)

    def test_rejects_rectangular_pattern_without_instances(self):
        c={"op":"create_rectangular_pattern","unit":"mm","feature_names":["Rib1"],"count_x":1,"count_y":1}
        with self.assertRaises(InventorBridgeError): validate_pattern(c)


if __name__ == "__main__": unittest.main()
