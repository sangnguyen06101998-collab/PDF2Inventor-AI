import unittest
from inventor_bridge import InventorBridgeError
from inventor_assembly import validate_assembly_command


class AssemblyValidationTests(unittest.TestCase):
    def test_valid_iam_manifest(self):
        c={"op":"create_assembly_iam","output_path":"C:/CAD/Assembly.iam",
           "components":[{"ipt_path":"C:/CAD/Base.ipt","position_mm":[0,0,0]},
                         {"ipt_path":"C:/CAD/Bracket.ipt","position_mm":[0,0,50]}]}
        self.assertEqual(len(validate_assembly_command(c)["components"]),2)

    def test_rejects_non_iam_output(self):
        c={"op":"create_assembly_iam","output_path":"C:/CAD/Assembly.ipt",
           "components":[{"ipt_path":"C:/CAD/Base.ipt"}]}
        with self.assertRaises(InventorBridgeError): validate_assembly_command(c)

    def test_rejects_bad_transform(self):
        c={"op":"create_assembly_iam","output_path":"C:/CAD/Assembly.iam",
           "components":[{"ipt_path":"C:/CAD/Base.ipt","position_mm":[0,0,"bad"]}]}
        with self.assertRaises(InventorBridgeError): validate_assembly_command(c)


if __name__ == "__main__": unittest.main()
