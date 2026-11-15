import unittest
from inventor_bridge import InventorBridgeError
from inventor_assembly_advanced import validate_assembly_constraints, validate_interference


class AssemblyAdvancedValidationTests(unittest.TestCase):
    def test_mate_and_flush_constraints(self):
        command = {
            "op": "create_assembly_constraints",
            "constraints": [
                {"type": "mate",
                 "entity_one": {"occurrence": "Base:1", "kind": "face", "index": 1},
                 "entity_two": {"occurrence": "Plate:1", "kind": "work_plane", "index": 3},
                 "offset_mm": 0},
                {"type": "flush",
                 "entity_one": {"occurrence": "Base:1", "kind": "work_plane", "index": 2},
                 "entity_two": {"occurrence": "Plate:1", "kind": "face", "index": 2},
                 "offset_mm": 1.5}
            ]
        }
        self.assertEqual(len(validate_assembly_constraints(command)["constraints"]), 2)

    def test_insert_uses_two_edges(self):
        command = {
            "op": "create_assembly_constraints",
            "constraints": [{
                "type": "insert",
                "entity_one": {"occurrence": "Shaft:1", "kind": "edge", "index": 1},
                "entity_two": {"occurrence": "Pulley:1", "kind": "edge", "index": 2},
                "axes_opposed": True, "offset_mm": 0
            }]
        }
        self.assertEqual(validate_assembly_constraints(command)["constraints"][0]["type"], "insert")

    def test_rejects_same_occurrence(self):
        command = {
            "op": "create_assembly_constraints",
            "constraints": [{
                "type": "mate",
                "entity_one": {"occurrence": "Base:1", "kind": "face", "index": 1},
                "entity_two": {"occurrence": "Base:1", "kind": "face", "index": 2}
            }]
        }
        with self.assertRaises(InventorBridgeError):
            validate_assembly_constraints(command)

    def test_interference_defaults_to_all_occurrences(self):
        cfg = validate_interference({"op": "analyze_assembly_interference"})
        self.assertEqual(cfg["occurrence_names"], [])

    def test_rejects_duplicate_occurrences(self):
        with self.assertRaises(InventorBridgeError):
            validate_interference({
                "op": "analyze_assembly_interference",
                "occurrence_names": ["A:1", "A:1"]
            })


if __name__ == "__main__":
    unittest.main()
