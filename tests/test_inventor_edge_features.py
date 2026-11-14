import unittest
from inventor_bridge import InventorBridgeError
from inventor_edge_features import validate_edge_finish


class EdgeFinishValidationTests(unittest.TestCase):
    def test_valid_fillet(self):
        c={"op":"create_fillet","unit":"mm","edge_indices":[1,3,4],"radius":2.5}
        self.assertEqual(validate_edge_finish(c)["radius"],2.5)

    def test_valid_chamfer(self):
        c={"op":"create_chamfer","unit":"mm","edge_indices":[2],"distance":1}
        self.assertEqual(validate_edge_finish(c)["edge_indices"],[2])

    def test_rejects_duplicate_edges(self):
        c={"op":"create_fillet","unit":"mm","edge_indices":[1,1],"radius":2}
        with self.assertRaises(InventorBridgeError): validate_edge_finish(c)

    def test_rejects_nonpositive_size(self):
        c={"op":"create_chamfer","unit":"mm","edge_indices":[1],"distance":0}
        with self.assertRaises(InventorBridgeError): validate_edge_finish(c)

    def test_rejects_implicit_units(self):
        c={"op":"create_fillet","edge_indices":[1],"radius":2}
        with self.assertRaises(InventorBridgeError): validate_edge_finish(c)


if __name__ == "__main__":
    unittest.main()
