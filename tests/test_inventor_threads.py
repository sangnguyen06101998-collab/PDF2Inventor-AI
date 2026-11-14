import unittest
from inventor_bridge import InventorBridgeError
from inventor_threads import validate_thread


class ThreadValidationTests(unittest.TestCase):
    def valid(self):
        return {"op":"create_thread","unit":"mm","face_index":2,"start_edge_index":1,
                "designation":"M8x1.25","thread_type":"ISO Metric Profile","thread_class":"6H",
                "internal":True,"right_handed":True,"full_depth":False,"depth_mm":12}
    def test_valid_metric_thread(self):
        c=validate_thread(self.valid())
        self.assertEqual(c["designation"],"M8x1.25")
        self.assertEqual(c["depth_mm"],12)
    def test_rejects_missing_units(self):
        c=self.valid(); c.pop("unit")
        with self.assertRaises(InventorBridgeError): validate_thread(c)
    def test_rejects_bad_face_index(self):
        c=self.valid(); c["face_index"]=0
        with self.assertRaises(InventorBridgeError): validate_thread(c)
    def test_requires_depth_for_partial_thread(self):
        c=self.valid(); c.pop("depth_mm")
        with self.assertRaises(InventorBridgeError): validate_thread(c)


if __name__=="__main__": unittest.main()
