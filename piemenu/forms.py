"""Load Designer forms while retaining FreeCAD's existing translations."""

import os

from PySide import QtCore, QtWidgets
try:
    from PySide import QtUiTools
except ImportError:
    try:
        from PySide6 import QtUiTools
    except ImportError:
        from PySide2 import QtUiTools

from . import resources


class Form:
    """Keep a form alive and expose its named widgets and layouts."""

    def __init__(self, root):
        self.root = root
        self._objects = {
            obj.objectName(): obj
            for obj in root.findChildren(QtCore.QObject)
            if obj.objectName()
        }

    def __getattr__(self, name):
        try:
            return self._objects[name]
        except KeyError:
            raise AttributeError(
                "The form {!r} has no object named {!r}".format(
                    self.root.objectName(), name)) from None


def _translate_form(root, translate):
    """Use the original TS contexts instead of changing existing catalogs."""
    for obj in [root] + root.findChildren(QtCore.QObject):
        for name in ("text", "title", "toolTip", "placeholderText"):
            context = obj.property("_translationContext_" + name)
            if context:
                source = obj.property(name)
                obj.setProperty(name, translate(context, source))
        if obj.inherits("QTabWidget"):
            for index in range(obj.count()):
                context = obj.widget(index).property("_translationContext_tabTitle")
                if context:
                    obj.setTabText(index, translate(context, obj.tabText(index)))
        if obj.inherits("QTableWidget"):
            for column in range(obj.columnCount()):
                context = obj.property("_translationContext_column" + str(column))
                header = obj.horizontalHeaderItem(column)
                if context and header:
                    header.setText(translate(context, header.text()))


def load_form(filename, parent=None, custom_widgets=(), translate=None):
    """Load a form relative to the add-on, registering custom Qt subclasses."""
    filename = os.path.join(resources.uipath, filename)
    loader = QtUiTools.QUiLoader()
    for widget in custom_widgets:
        loader.registerCustomWidget(widget)
    loader.setWorkingDirectory(QtCore.QDir(resources.uipath))
    ui_file = QtCore.QFile(filename)
    if not ui_file.open(QtCore.QIODevice.ReadOnly):
        raise RuntimeError("Cannot open UI form {!r}: {}".format(
            filename, ui_file.errorString()))
    try:
        root = loader.load(ui_file, parent)
    finally:
        ui_file.close()
    if root is None:
        raise RuntimeError("Cannot load UI form {!r}: {}".format(
            filename, loader.errorString()))
    if translate is not None:
        _translate_form(root, translate)
    for table in root.findChildren(QtWidgets.QTableWidget):
        header = table.horizontalHeader()
        header.setResizeContentsPrecision(-1)
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
    return Form(root)
