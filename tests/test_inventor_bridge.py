import tempfile
import unittest
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import inventor_bridge

from inventor_bridge import (
    InventorBridgeError,
    _format_expression,
    _parse_expression,
    apply_parameter_changes,
    read_parameters,
)


class FakeParameter:
    def __init__(self, name, expression):
        self.Name = name
        self.Expression = expression


class FakeParameterCollection:
    def __init__(self, parameters):
        self._items = {p.Name: p for p in parameters}

    @property
    def Count(self):
        return len(self._items)

    def Item(self, key):
        if isinstance(key, int):
            values = list(self._items.values())
            if key < 1 or key > len(values):
                raise IndexError(key)
            return values[key - 1]
        return self._items[key]


class FakeComponentDefinition:
    def __init__(self, parameters):
        self.Parameters = FakeParameterCollection(parameters)


class FakeDocument:
    def __init__(self, file_path, parameters, fail_first_update=False):
        self.FullFileName = str(file_path)
        self.DisplayName = Path(file_path).name
        self.ComponentDefinition = FakeComponentDefinition(parameters)
        self.fail_next_update = fail_first_update
        self.update_count = 0
        self.save_count = 0

    def Save(self):
        self.save_count += 1

    def Update(self):
        self.update_count += 1
        if self.fail_next_update:
            self.fail_next_update = False
            raise RuntimeError("simulated update failure")


class FakeRawDispatch:
    def QueryInterface(self, _iid):
        return SimpleNamespace(SoftwareVersion=SimpleNamespace(DisplayVersion="2018"))


class FakePythonCom:
    IID_IDispatch = object()

    def __init__(self, fail_active=False):
        self.initialized = 0
        self.fail_active = fail_active

    def CoInitialize(self):
        self.initialized += 1

    def CLSIDFromProgID(self, progid):
        if progid != "Inventor.Application":
            raise ValueError(progid)
        return "{FAKE-INVENTOR-CLSID}"

    def GetActiveObject(self, clsid):
        if self.fail_active:
            error = RuntimeError("Operation unavailable")
            error.hresult = -2147221021
            raise error
        if clsid != "{FAKE-INVENTOR-CLSID}":
            raise ValueError(clsid)
        return FakeRawDispatch()


class InventorBridgeTests(unittest.TestCase):
    def test_connect_initializes_com_and_attaches_to_running_inventor(self):
        fake_pythoncom = FakePythonCom()
        fake_pywintypes = SimpleNamespace(IID=lambda value: "{FAKE-INVENTOR-CLSID}")
        client_module = ModuleType("win32com.client")
        client_module.Dispatch = lambda dispatch: dispatch.QueryInterface(None)
        win32com_module = ModuleType("win32com")
        win32com_module.client = client_module

        with patch.dict(sys.modules, {
            "pythoncom": fake_pythoncom,
            "pywintypes": fake_pywintypes,
            "win32com": win32com_module,
            "win32com.client": client_module,
        }):
            inventor_bridge._COM_INITIALIZED = False
            app = inventor_bridge.connect_inventor()

        self.assertEqual(fake_pythoncom.initialized, 1)
        self.assertEqual(app.SoftwareVersion.DisplayVersion, "2018")

    def test_connect_error_includes_hresult_diagnostic(self):
        fake_pythoncom = FakePythonCom(fail_active=True)
        fake_pywintypes = SimpleNamespace(IID=lambda value: "{FAKE-INVENTOR-CLSID}")
        client_module = ModuleType("win32com.client")
        win32com_module = ModuleType("win32com")
        win32com_module.client = client_module

        with patch.dict(sys.modules, {
            "pythoncom": fake_pythoncom,
            "win32com": win32com_module,
            "win32com.client": client_module,
        }):
            inventor_bridge._COM_INITIALIZED = False
            with self.assertRaises(InventorBridgeError) as context:
                inventor_bridge.connect_inventor()

        self.assertIn("0x800401E3", str(context.exception))
        self.assertIn("cùng mức quyền", str(context.exception))

    def test_parse_expression_with_length_unit(self):
        parsed = _parse_expression("150 mm")
        self.assertEqual(parsed["value"], 150)
        self.assertEqual(parsed["unit"], "mm")
        self.assertEqual(parsed["expression"], "150 mm")

    def test_parse_expression_with_angle_unit(self):
        parsed = _parse_expression("0 deg")
        self.assertEqual(parsed["value"], 0)
        self.assertEqual(parsed["unit"], "deg")

    def test_format_expression_rejects_boolean(self):
        with self.assertRaises(InventorBridgeError):
            _format_expression(True, "mm")

    def test_format_expression_rejects_unknown_unit(self):
        with self.assertRaises(InventorBridgeError):
            _format_expression(10, "widgets")

    def test_read_parameters_returns_json_safe_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.ipt"
            path.write_bytes(b"fake IPT")
            doc = FakeDocument(path, [
                FakeParameter("Length", "100 mm"),
                FakeParameter("Angle", "0 deg"),
            ])
            params = read_parameters(doc)
            self.assertEqual(params["Length"]["value"], 100)
            self.assertEqual(params["Length"]["unit"], "mm")
            self.assertEqual(params["Angle"]["unit"], "deg")

    def test_apply_parameter_change_creates_backup_and_saves(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.ipt"
            path.write_bytes(b"fake IPT")
            doc = FakeDocument(path, [FakeParameter("Length", "100 mm")])

            result = apply_parameter_changes(
                doc, [{"parameter": "Length", "value": 150, "unit": "mm"}]
            )

            self.assertEqual(doc.ComponentDefinition.Parameters.Item("Length").Expression, "150 mm")
            self.assertTrue(Path(result["backup_path"]).is_file())
            self.assertEqual(result["updated"]["Length"], "150 mm")
            self.assertEqual(result["parameters"]["Length"]["value"], 150)
            self.assertGreaterEqual(doc.save_count, 2)

    def test_failed_update_rolls_back_previous_expression(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.ipt"
            path.write_bytes(b"fake IPT")
            doc = FakeDocument(
                path, [FakeParameter("Length", "100 mm")], fail_first_update=True
            )

            with self.assertRaises(InventorBridgeError) as context:
                apply_parameter_changes(
                    doc, [{"parameter": "Length", "value": 150, "unit": "mm"}]
                )

            self.assertEqual(doc.ComponentDefinition.Parameters.Item("Length").Expression, "100 mm")
            self.assertIn("Đã khôi phục", str(context.exception))
            self.assertEqual(doc.update_count, 2)


if __name__ == "__main__":
    unittest.main()
