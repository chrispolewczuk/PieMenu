"""Exercise the real startup guard and settings opener without FreeCAD."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock


SOURCE = Path(__file__).resolve().parents[1] / "InitGui.py"


def startup_node():
    module = ast.parse(SOURCE.read_text(encoding="utf-8"))
    return next(node for node in module.body
                if isinstance(node, ast.FunctionDef) and node.name == "pieMenuStart")


class SettingsLifecycleTests(unittest.TestCase):
    def test_opening_settings_twice_keeps_the_existing_dialog(self):
        opener = next(node for node in startup_node().body
                      if isinstance(node, ast.FunctionDef) and node.name == "onControl")
        dialog = MagicMock()
        dialog.objectName.return_value = "PieMenuPreferences"
        window = MagicMock()
        window.findChildren.return_value = [dialog]
        namespace = {name: MagicMock() for name in (
            "Gui", "getPieName", "getParam", "cBoxUpdate", "buttonList", "tabs",
            "labelGlobalShortcut", "getShape", "onShape", "updateIconsPieMenus",
            "updatePiemenuPreview", "cBox", "QtGui",
        )}
        namespace.update(
            mw=window, pieMenuDialog=dialog,
            state=SimpleNamespace(app_state=SimpleNamespace(global_shortcut_key="TAB")),
            translate=lambda _context, text: text,
        )
        exec(compile(ast.Module(body=[opener], type_ignores=[]), str(SOURCE), "exec"),
             namespace)
        namespace["onControl"]("View")
        namespace["onControl"]("View")
        self.assertEqual(dialog.show.call_count, 2)
        dialog.deleteLater.assert_not_called()
        namespace["tabs"].deleteLater.assert_not_called()

    def test_duplicate_start_returns_before_rebuilding_settings(self):
        startup = startup_node()
        guard_index, guard = next(
            (index, node) for index, node in enumerate(startup.body)
            if isinstance(node, ast.If) and "PieMenuShortCut" in ast.unparse(node.test))
        first_class = next(index for index, node in enumerate(startup.body)
                           if isinstance(node, ast.ClassDef))
        self.assertLess(guard_index, first_class)
        probe = ast.FunctionDef(
            name="start_probe", args=startup.args,
            body=[guard, ast.Return(value=ast.Constant(value="build UI"))],
            decorator_list=[],
        )
        module = ast.fix_missing_locations(ast.Module(body=[probe], type_ignores=[]))
        gui = MagicMock()
        namespace = {"Gui": gui, "QtGui": MagicMock()}
        exec(compile(module, str(SOURCE), "exec"), namespace)
        gui.getMainWindow.return_value.findChild.return_value = object()
        self.assertIsNone(namespace["start_probe"]())
        gui.getMainWindow.return_value.findChild.return_value = None
        self.assertEqual(namespace["start_probe"](), "build UI")


if __name__ == "__main__":
    unittest.main()
