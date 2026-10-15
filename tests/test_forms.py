"""Load the Designer forms with Qt, including their custom widget hooks."""

import ast
import gc
from pathlib import Path
import unittest
from types import SimpleNamespace

try:
    from PySide import QtCore, QtWidgets
    from piemenu.forms import load_form
except ImportError:
    QtWidgets = None


if QtWidgets is not None:
    class PieMenuDialog(QtWidgets.QDialog):
        pass

    class CustomLineEdit(QtWidgets.QLineEdit):
        pass


@unittest.skipIf(QtWidgets is None, "Qt UI tools are unavailable")
class DesignerFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.forms = []

    def tearDown(self):
        for form in self.forms:
            form.root.deleteLater()
        self.app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)

    def preferences(self, translate=None):
        form = load_form("PieMenuPreferences.ui", custom_widgets=(
            PieMenuDialog, CustomLineEdit), translate=translate)
        self.forms.append(form)
        return form

    def test_preferences_load_custom_widgets_and_tools_columns(self):
        form = self.preferences()
        self.assertIsInstance(form.root, PieMenuDialog)
        self.assertEqual(form.root.objectName(), "PieMenuPreferences")
        self.assertIsInstance(form.shortcutLineEdit, CustomLineEdit)
        self.assertIsInstance(form.globalShortcutLineEdit, CustomLineEdit)
        self.assertEqual(form.toolListWidget.columnCount(), 4)
        self.assertEqual([form.toolListWidget.horizontalHeaderItem(i).text()
                          for i in range(4)], ["Inner", "Outer", "Tools", "Workbench"])

    def test_runtime_bindings_match_the_designer_form(self):
        form = self.preferences()
        source = Path(__file__).resolve().parents[1] / "InitGui.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "settings_form"):
                with self.subTest(object_name=node.attr):
                    self.assertIsNotNone(getattr(form, node.attr))

    def test_trigger_mode_buttons_survive_startup_garbage_collection(self):
        source = Path(__file__).resolve().parents[1] / "InitGui.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        startup = next(node for node in tree.body
                       if isinstance(node, ast.FunctionDef) and node.name == "pieMenuStart")
        group_setup = [node for node in startup.body if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "radioGroup"
                    for target in node.targets)) or (
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "radioGroup")]

        def initialize():
            form = load_form("PieMenuPreferences.ui", custom_widgets=(
                PieMenuDialog, CustomLineEdit))
            namespace = dict(
                QtGui=SimpleNamespace(QButtonGroup=QtWidgets.QButtonGroup),
                pieMenuDialog=form.root, radioButtonPress=form.radioButtonPress,
                radioButtonHover=form.radioButtonHover)
            exec(compile(ast.Module(body=group_setup, type_ignores=[]),
                         str(source), "exec"), namespace)
            return form.root, form.radioButtonPress, form.radioButtonHover

        root, press, hover = initialize()
        self.addCleanup(root.deleteLater)
        gc.collect()
        self.app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        press.setChecked(True)
        hover.setChecked(True)
        self.assertTrue(hover.isChecked())
        self.assertFalse(press.isChecked())
        self.assertIs(press.group().parent(), root)

    def test_settings_pages_and_default_layout(self):
        form = self.preferences()
        self.assertEqual(form.tabs.count(), 4)
        self.assertEqual(form.vSplitter.count(), 4)
        self.assertTrue(form.toolBarTab.isHidden())
        self.assertEqual(form.iconSpacingGroup.title(), "Icon Spacing")
        self.assertTrue(form.radioInnerEquallySpaced.isChecked())
        self.assertTrue(form.radioOuterEquallySpaced.isChecked())
        self.assertFalse(form.radioInnerPacked.isChecked())
        self.assertFalse(form.radioOuterPacked.isChecked())
        self.assertEqual(form.spinButton.minimum(), 16)
        self.assertEqual(form.spinButton.maximum(), 120)
        self.assertEqual(form.contextTable.rowCount(), 6)
        self.assertEqual(form.contextTable.columnCount(), 3)
        self.assertFalse(form.buttonAddPieMenu.icon().isNull())

    def test_all_panel_tables_fit_contents_and_stretch_the_last_column(self):
        form = self.preferences()
        for table in form.root.findChildren(QtWidgets.QTableWidget):
            header = table.horizontalHeader()
            with self.subTest(table=table.objectName()):
                self.assertTrue(header.stretchLastSection())
                self.assertEqual(header.resizeContentsPrecision(), -1)
                for column in range(table.columnCount()):
                    self.assertEqual(header.sectionResizeMode(column),
                                     QtWidgets.QHeaderView.ResizeToContents)

    def test_tools_columns_fit_new_content_and_last_column_fills_extra_width(self):
        form = self.preferences()
        table = form.toolListWidget
        table.setRowCount(1)
        for column, text in enumerate(("", "", "Short", "Part")):
            table.setItem(0, column, QtWidgets.QTableWidgetItem(text))
        table.setFixedWidth(900)
        form.tabs.setCurrentWidget(form.widgetContainer)
        form.root.show()
        self.app.processEvents()
        short_width = table.columnWidth(2)
        table.item(0, 2).setText("A much longer command name that should fit its column")
        self.app.processEvents()
        self.assertGreater(table.columnWidth(2), short_width)
        first_widths = [table.columnWidth(column) for column in range(3)]
        last_width = table.columnWidth(3)
        self.assertGreaterEqual(sum(first_widths) + last_width, table.viewport().width())
        table.setFixedWidth(1200)
        self.app.processEvents()
        self.assertEqual([table.columnWidth(column) for column in range(3)], first_widths)
        self.assertGreater(table.columnWidth(3), last_width)

    def test_legacy_translation_contexts_are_preserved(self):
        form = self.preferences(lambda context, source: context + ":" + source)
        self.assertEqual(form.shapeGroup.title(), "PieMenuTab:Shape")
        self.assertEqual(form.tabs.tabText(1), "ToolsTab:Tools")
        self.assertEqual(form.toolListWidget.horizontalHeaderItem(0).text(),
                         "ToolsTab:Inner")

    def test_ring_spacing_radio_groups_are_independent_and_exclusive(self):
        form = self.preferences()
        form.radioInnerPacked.click()
        self.assertTrue(form.radioInnerPacked.isChecked())
        self.assertFalse(form.radioInnerEquallySpaced.isChecked())
        self.assertTrue(form.radioOuterEquallySpaced.isChecked())
        form.radioOuterPacked.click()
        self.assertTrue(form.radioInnerPacked.isChecked())
        self.assertTrue(form.radioOuterPacked.isChecked())
        self.assertFalse(form.radioOuterEquallySpaced.isChecked())
        form.radioInnerEquallySpaced.click()
        self.assertFalse(form.radioInnerPacked.isChecked())
        self.assertTrue(form.radioOuterPacked.isChecked())

    def test_icon_picker_keeps_dynamic_icon_grid(self):
        form = load_form("IconPicker.ui")
        self.forms.append(form)
        self.assertEqual(form.grid_layout.count(), 0)
        self.assertIs(form.scroll_area.widget(), form.grid_widget)
        self.assertEqual(form.buttonBrowse.text(), "Browse Icons Files...")

    def test_icon_picker_stays_hidden_when_settings_open(self):
        preferences = self.preferences()
        icons = load_form("IconPicker.ui", preferences.root)
        self.forms.append(icons)
        preferences.root.show()
        self.app.processEvents()
        self.assertFalse(icons.root.isVisible())

    def test_shortcut_editor_loads_custom_key_field(self):
        form = load_form("ShortcutEditor.ui", custom_widgets=(CustomLineEdit,))
        self.forms.append(form)
        self.assertIsInstance(form.shortcutEdit, CustomLineEdit)
        self.assertIsNotNone(form.buttonBox.button(QtWidgets.QDialogButtonBox.Ok))
        self.assertIsNotNone(form.buttonBox.button(QtWidgets.QDialogButtonBox.Cancel))

    def test_missing_form_reports_filename(self):
        with self.assertRaisesRegex(RuntimeError, "MissingForm.ui"):
            load_form("MissingForm.ui")

    def test_missing_object_reports_its_name(self):
        form = self.preferences()
        with self.assertRaisesRegex(AttributeError, "missingWidget"):
            _ = form.missingWidget


if __name__ == "__main__":
    unittest.main()
