# PieMenu widget for FreeCAD

# Copyright (C) 2026 Ben-PH,
# Copyright (C) 2024 Grubuntu, Pgilfernandez, hasecilu @ FreeCAD
# Copyright (C) 2022, 2023 mdkus @ FreeCAD
# Copyright (C) 2016, 2017 triplus @ FreeCAD
# Copyright (C) 2015,2016 looo @ FreeCAD
# Copyright (C) 2015 microelly <microelly2@freecadbuch.de>
#
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA

# Attribution:
# http://forum.freecadweb.org/
# http://www.freecadweb.org/wiki/index.php?title=Code_snippets
#

global PIE_MENU_VERSION
PIE_MENU_VERSION = "1.14"
def pieMenuStart():
    # piemenu directory imports
    from piemenu import constants, config, resources, state
    from piemenu.layout import outer_ring_positions
    from piemenu.forms import load_form

    """Main function that starts the Pie Menu."""
    import datetime
    import math
    import os
    import platform
    import shutil

    import FreeCAD as App
    import FreeCADGui as Gui
    from FreeCAD import Units
    from PySide import QtCore, QtGui, QtWidgets
    from PySide.QtCore import QSize, Qt
    from PySide.QtGui import QFontMetrics, QKeySequence, QShortcut, QTransform
    from PySide.QtWidgets import QCheckBox, QDialog, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidgetItem, QMessageBox, QVBoxLayout, QWidget

    from functools import partial

    # Workbench reloads must reuse the UI captured by the existing event filter.
    if Gui.getMainWindow().findChild(QtGui.QAction, "PieMenuShortCut") is not None:
        return

    global loadedWorkbenches
    loadedWorkbenches = config.get_loaded_workbenches()
    global sign
    sign = constants.get_signs()
    global sortOrder
    sortOrder = QtCore.Qt.AscendingOrder

    # Add translations path
    translate = App.Qt.translate
    Gui.addLanguagePath(resources.transpath)
    Gui.updateLocale()

    contextPhase = False

    # Target of the shared icon-picker window: when setIcon is not None the
    # grid picks an icon for a shortcut entry instead of the current PieMenu.
    iconPickerTarget = {"setIcon": None, "parent": None}

    # Object name prefix of the plain QActions backing shortcut entries.
    shortcutEntryPrefix = "PieMenu_ShortcutEntry_"


    # HACK: workaround to avoid ghosting : we find wbs already loaded,
    # so as not to reload them again in the function 'updateCommands'
    iconDefault = QtGui.QApplication.style().standardIcon(
        QtGui.QStyle.StandardPixmap.SP_DialogApplyButton)



    #### Classes definition ####
    class SelObserver:
        def addSelection(self, doc, obj, sub, pnt):
            # block listTopo as CTRL is press to allow multiple selection for context
            modifiers = QtGui.QApplication.keyboardModifiers()
            if not (modifiers & QtCore.Qt.ControlModifier):
                listTopo()

        def removeSelection(self, doc, obj, sub):
            # block listTopo as CTRL is press to allow multiple deselection for context
            modifiers = QtGui.QApplication.keyboardModifiers()
            if not (modifiers & QtCore.Qt.ControlModifier):
                listTopo()

    class CustomLineEdit(QLineEdit):
        """ get key event from box shortcut in settings """

        def __init__(self, parent=None):
            super(CustomLineEdit, self).__init__(parent)

        def keyPressEvent(self, event):
            key_text = QKeySequence(event.key()).toString()
            modifier_text = self.get_modifier_text(event.modifiers())

            # Tab key
            if event.key() == Qt.Key_Tab:
                self.setText("TAB")
                return

            elif event.key() in [Qt.Key_Backspace, Qt.Key_Delete]:
                if len(self.text()) > 0:
                    current_text = self.text()
                    if current_text and current_text[-1] == ',':
                        self.setText(current_text[:-1])
                    else:
                        self.setText(current_text[:-1])
                else:
                    self.setText('')

            elif modifier_text:
                if key_text and modifier_text:

                    shortcut_text = f"{modifier_text}+{key_text}"
                    self.setText(shortcut_text)

            elif key_text:
                if len(self.selectedText()) > 0:
                    self.setText(key_text)
                else:
                    if len(key_text) == 1 and len(self.text()) > 0:
                        last_char = self.text()[-1]
                        if last_char.isalpha():
                            self.setText(self.text() + ',' + key_text)
                        else:
                            self.setText(self.text() + key_text)
                    else:
                        self.setText(key_text)
            else:
                super().keyPressEvent(event)

            currentShortcut = self.text()
            shortcutsAssigned = getAssignedShortcut()
            compareAndDisplayWarning(
                shortcutsAssigned, currentShortcut, getattr(self, "warningLabel", None))

        def get_modifier_text(self, modifiers):
            # Dictionnaire des modificateurs
            modifier_names = {
                Qt.ControlModifier: 'CTRL',
                Qt.AltModifier: 'ALT',
                Qt.ShiftModifier: 'SHIFT',
                Qt.MetaModifier: 'META'
            }

            # Si aucun modificateur n'est présent, retourner une chaîne vide
            if modifiers == Qt.KeyboardModifier.NoModifier:
                return ""

            # Construction du texte pour les modificateurs actifs
            modifier_text = '+'.join(
                modifier_names[modifier]
                for modifier in modifier_names
                if modifiers & modifier
            )

            # Gestion de Qt.Key_Tab si nécessaire
            if modifiers == Qt.Key_Tab:
                modifier_text += '+TAB' if modifier_text else 'TAB'

            return modifier_text

    class HoverButton(QtGui.QToolButton):
        """ Custom class : hover timer to avoid too fast triggering on hover mode """

        def __init__(self, parent=None):
            super(HoverButton, self).__init__()
            self.hoverTimer = QtCore.QTimer(self)
            self.hoverTimer.setSingleShot(True)
            self.hoverTimer.timeout.connect(self.onHoverTimeout)
            self.enterEventConnected = False
            self.isMouseOver = False
            self.leaveEvent = self.onLeaveEvent

        def onHoverTimeout(self):
            """Handle hover timeout event."""
            global triggerMode
            mode = triggerMode
            if self.isMouseOver and self.defaultAction().isEnabled() and mode == "Hover":
                if not pieMenuDialog.isVisible():
                    PieMenuInstance.hide()
                    self.defaultAction().trigger()
                    module = None
                    try:
                        g = Gui.ActiveDocument.getInEdit()
                        module = g.Module
                    except:
                        pass
                    displaySpinBox = getParameterGlobal("Bool", "DisplaySpinBox")
                    if (module is not None and module != 'SketcherGui') and displaySpinBox:
                        PieMenuInstance.showAtMouseInstance()
            else:
                pass

        def onLeaveEvent(self, event):
            self.isMouseOver = False

        def enterEvent(self, event):

            if not self.enterEventConnected:
                self.hoverTimer.start(state.app_state.hover_delay)
                self.enterEventConnected = True
            self.hoverTimer.stop()
            self.hoverTimer.start(state.app_state.hover_delay)
            self.isMouseOver = True

        def mouseReleaseEvent(self, event):
            if self.isMouseOver and self.defaultAction().isEnabled():
                if not pieMenuDialog.isVisible():
                    PieMenuInstance.hide()
                    mw.setFocus()
                    self.defaultAction().trigger()
                    module = None
                    try:
                        g = Gui.ActiveDocument.getInEdit()
                        module = g.Module
                        fonctionActive = g.Object
                        displaySpinBox = getParameterGlobal("Bool", "DisplaySpinBox")

                        if (module is not None and module != 'SketcherGui' and str(fonctionActive) in constants.listSpinboxFeatures) and displaySpinBox:
                            PieMenuInstance.showAtMouseInstance()
                    except:
                        pass
            else:
                pass

    class PreselectButton(QtGui.QToolButton):
        """ Custom class : for preselect button """

        def __init__(self, parent=None):
            super(PreselectButton, self).__init__()
            self.baseIcon = None
            self.hoverIcon = None
            self.leaveEvent = self.onLeaveEvent

        def onLeaveEvent(self, event):
            self.setIcon(self.baseIcon)
            self.update()

        def enterEvent(self, event):
            self.setIcon(self.hoverIcon)
            self.update()

        def mouseReleaseEvent(self, event):
            if self.defaultAction().isEnabled():
                if not pieMenuDialog.isVisible():
                    PieMenuInstance.hide()
                    mw.setFocus()
                    self.defaultAction().trigger()
                    module = None
                    try:
                        g = Gui.ActiveDocument.getInEdit()
                        module = g.Module
                        fonctionActive = g.Object
                        displaySpinBox = getParameterGlobal("Bool", "DisplaySpinBox")
                        if (module is not None and module != 'SketcherGui' and str(fonctionActive) in constants.listSpinboxFeatures) and displaySpinBox:
                            PieMenuInstance.showAtMouseInstance()
                    except:
                        pass
            else:
                pass

        def setBaseIcon(self, icon=QtGui.QIcon()):
            self.baseIcon = icon
            self.setIcon(self.baseIcon)

        def setHoverIcon(self, icon=QtGui.QIcon()):
            self.hoverIcon = icon

    class PieMenuSeparator():
        """Class PieMenuSeparator"""

        def __init__(self):
            pass

        def GetResources(self):
            """Return a dictionary with data that will be used by the button or menu item."""
            return {'Pixmap': resources.iconAddSeparator,
                    'MenuText': translate('PieMenuTab', 'Separator'),
                    'ToolTip': translate('PieMenuTab', 'Separator for PieMenu ')}

        def Activated(self):
            """Run the following code when the command is activated (button press)."""
            pass

        def IsActive(self):
            """Return True when the command should be active or False when it should be disabled (greyed)."""
            return False

    class NestedPieMenu():
        """Class nested PieMenu """

        def __init__(self, keyValue, iconPath=None):
            self.iconPath = resources.iconPieMenuLogo
            self.keyValue = keyValue

        def GetResources(self):
            """Return a dictionary with data that will be used by the button or menu item."""
            return {'Pixmap': self.iconPath,
                    'MenuText': self.keyValue,
                    'ToolTip': self.keyValue,
                    'CmdType': 'ForEdit'}

        def Activated(self):
            """Run the following code when the command is activated (button press)."""
            PieMenuInstance.showAtMouseInstance(self.keyValue)

        def IsActive(self):
            """Return True when the command should be active or False when it should be disabled (greyed)."""
            return True

        def setIconPath(self, icon_path):
            """Set the icon path for the NestedPieMenu instance."""
            self.iconPath = icon_path

    #### Class PieMenu ####

    class PieMenu(QWidget):
        """ Main widget for PieMenu """
        mw = Gui.getMainWindow()
        event_filter_installed = False
        offset_x = 0
        offset_y = 0

        def __init__(self, parent=mw):
            super().__init__(parent)
            self.double_spinbox = None
            styleCurrentTheme = getStyle()

            # timer for right click delay
            self.timer = QtCore.QTimer(self)
            self.timer.setSingleShot(True)
            self.timer.timeout.connect(self.show_menu)

            self.debounceTimer = QtCore.QTimer(self)
            self.debounceTimer.setSingleShot(True)
            self.debounceTimer.timeout.connect(self.install_filter)

            if not PieMenu.event_filter_installed:
                app = QtGui.QGuiApplication.instance() or QtGui.QApplication([])
                app.installEventFilter(self)
                PieMenu.event_filter_installed = True

            self.radius = 100
            self.buttons = []
            self.buttonSize = 32

            self.menu = QtWidgets.QWidget(None)
            self.menu.setObjectName("styleContainer")
            self.menu.setStyleSheet(styleCurrentTheme)

            flags = QtCore.Qt.FramelessWindowHint | QtCore.Qt.Popup | QtCore.Qt.NoDropShadowWindowHint
            # flags = QtCore.Qt.FramelessWindowHint | QtCore.Qt.Popup

            self.menu.setWindowFlags(flags)
            self.menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)

            self.menuSize = self.radius * 2 + self.buttonSize

            if compositingManager:
                pass
            else:
                self.menu.setAttribute(QtCore.Qt.WA_PaintOnScreen)

        def stop_filter(self):
            app = QtGui.QGuiApplication.instance() or QtGui.QApplication([])
            app.removeEventFilter(self)

        def install_filter(self):
            app = QtGui.QGuiApplication.instance() or QtGui.QApplication([])
            app.installEventFilter(self)

        def show_menu(self):
            if self.menu.isVisible():
                self.menu.hide()
            else:
                actionKey.trigger()

        def validation(self):
            # fix https://github.com/Grubuntu/PieMenu/issues/130
            # quit current sketcher operation:
            Gui.runCommand("Sketcher_StopOperation")
            # to avoid that 'Sketcher_CompDimensionTools' being activated before resetEdit()
            Gui.ActiveDocument.resetEdit()
            App.ActiveDocument.recompute()
            PieMenuInstance.hide()

        def cancel(self):
            docName = App.ActiveDocument.Name
            # quit current sketcher operation:
            Gui.runCommand("Sketcher_StopOperation")
            App.closeActiveTransaction(True)
            Gui.Control.closeDialog()
            App.getDocument(docName).recompute()
            Gui.getDocument(docName).resetEdit()
            PieMenuInstance.hide()

        def validButton(self, buttonSize=32):
            icon = iconSize(buttonSize)
            button = QtGui.QToolButton()
            button.setObjectName("styleComboValid")
            button.setProperty("ButtonX", -25)
            button.setProperty("ButtonY", 8)
            button.setGeometry(0, 0, buttonSize, buttonSize)
            button.setIconSize(QtCore.QSize(icon, icon))
            return button

        def cancelButton(self, buttonSize=32):
            icon = iconSize(buttonSize)
            button = QtGui.QToolButton()
            button.setObjectName("styleComboCancel")
            button.setProperty("ButtonX", 25)
            button.setProperty("ButtonY", 8)
            button.setGeometry(0, 0, buttonSize, buttonSize)
            button.setIconSize(QtCore.QSize(icon, icon))
            return button

        def settingsButton(self, keyValue, buttonSize=32):
            """Open settings from an otherwise empty pie center."""
            button = QtGui.QToolButton(self.menu)
            button.setObjectName("pieMenu")
            button.setProperty("ButtonX", 0)
            button.setProperty("ButtonY", 0)
            button.setGeometry(0, 0, buttonSize, buttonSize)
            icon = int(iconSize(buttonSize))
            button.setIconSize(QtCore.QSize(icon, icon))
            button.setIcon(QtGui.QIcon(resources.iconPieMenuLogo))
            button.setToolTip(translate("AccesoriesMenu", "Open PieMenu settings"))
            button.setStyleSheet(getStyle() + radiusSize(buttonSize))

            def openSettings():
                self.hide()
                onControl(keyValue)

            button.clicked.connect(openSettings)
            return button

        def doubleSpinbox(self, buttonSize=32, step=1.0):
            """ https://github.com/FreeCAD/FreeCAD/blob/main/src/Gui/QuantitySpinBox.h """
            ui = Gui.UiLoader()
            button = ui.createWidget("Gui::QuantitySpinBox")
            button.setProperty("minimum", 0.0)
            button.setFixedWidth(110)
            button.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
            button.setProperty("ButtonX", 0)
            button.setProperty("ButtonY", -30)
            button.setAttribute(QtCore.Qt.WA_TranslucentBackground)
            button.setStyleSheet(" QWidget { border-radius: 5px; }")
            button.setProperty("setSingleStep", step)
            button.valueChanged.connect(self.spin_interactif)
            return button

        def checkboxThroughAll(self):
            checkboxThroughAll = QCheckBox(
                translate("Fast Spinbox", "Through all"))
            checkboxThroughAll.setCheckable(True)
            checkboxThroughAll.setProperty("ButtonX", 50)
            checkboxThroughAll.setProperty("ButtonY", -105)
            checkboxThroughAll.setAttribute(QtCore.Qt.WA_TranslucentBackground)
            return checkboxThroughAll

        def checkboxReversed(self):
            checkboxReversed = QCheckBox(translate("Fast Spinbox", "Reversed"))
            checkboxReversed.setCheckable(True)
            checkboxReversed.setProperty("ButtonX", 50)
            checkboxReversed.setProperty("ButtonY", -55)
            checkboxReversed.setAttribute(QtCore.Qt.WA_TranslucentBackground)
            return checkboxReversed

        def checkboxSymToPlane(self):
            checkboxSymToPlane = QCheckBox(
                translate("Fast Spinbox", "Symmetric to plane"))
            checkboxSymToPlane.setCheckable(True)
            checkboxSymToPlane.setProperty("ButtonX", 50)
            checkboxSymToPlane.setProperty("ButtonY", -80)
            checkboxSymToPlane.setAttribute(QtCore.Qt.WA_TranslucentBackground)
            return checkboxSymToPlane

        def eventFilter(self, obj, event):
            """Handle mouse and keyboard events """
            if event.type() == QtCore.QEvent.MouseButtonRelease:
                if event.button() == QtCore.Qt.LeftButton:
                    if self.menu.isActiveWindow() or pieMenuDialog.isVisible():
                        pass
                    else:
                        self.menu.hide()
                        for i in self.buttons:
                            i.hide()
                        return False

            try:
                if checkboxRightClick.isChecked():
                    if event.type() == QtCore.QEvent.MouseButtonPress:
                        if event.button() == QtCore.Qt.RightButton:
                            self.timer.start(spinDelayRightClick.value())
                            return False

                    if event.type() == QtCore.QEvent.MouseButtonRelease:
                        if event.button() == QtCore.Qt.RightButton:
                            if self.timer.isActive():
                                self.timer.stop()
                                self.debounceTimer.start(100)
                                self.stop_filter()
                                return False
                            else:
                                return True
            except:
                None

            # Special case when shortcut is assigned to tool PieMenu AND also other there
            if event.type() == QtCore.QEvent.ShortcutOverride and self.menu.isVisible():
                # we need to set "state.app_state.flag_shortcut_override" to advertise that we go through Event.ShortcutOverride for this tool shortcut for the step "KeyRelease" below
                state.app_state.flag_shortcut_override = False
                key = event.key()
                event.accept()
                try:
                    # if fast spinbox is open, we do nothing with shortcuts
                    if self.double_spinbox.isVisible():
                        pass
                except:
                    # spinbox not show
                    try:
                        charKey = chr(key)
                    except:
                        charKey = ''
                    if charKey in state.app_state.list_shortcut_code:
                        self.menu.hide()
                        j = 0
                        for i in state.app_state.list_shortcut_code:
                            if i == charKey:
                                # set flag here
                                state.app_state.flag_shortcut_override = True
                            j += 1
                        return True
                    # Handle toggle mode for global shortcut###
                    elif checkboxGlobalKeyToggle.isChecked():
                        if event.key() == QtGui.QKeySequence(state.app_state.global_shortcut_key):
                            if self.menu.isVisible():
                                self.menu.hide()
                                return True
                            else:
                                return False

                        for shortcut in mw.findChildren(QShortcut):
                            if event.key() == QtGui.QKeySequence(shortcut.key()):
                                if self.menu.isVisible():
                                    self.menu.hide()
                                    event.accept()
                                    return True
                                else:
                                    return False

            """ Handle keys Return and Enter for spinbox """
            if event.type() == QtCore.QEvent.KeyPress:
                key = event.key()
                #### Confirm with 'Enter' or 'Return' key ####
                if key == QtCore.Qt.Key_Enter or key == QtCore.Qt.Key_Return:
                    try:
                        if self.double_spinbox.isVisible():
                            self.validation()
                    except:
                        None
                    try:
                        if self.menu.isVisible():
                            self.validation()
                    except:
                        None
                        return True

                #### Keys SUPPR, DEL, UP and DOWN in Toollist ####
                """ Handle Keys SUPPR, DEL, UP and DOWN in Toollist """
                # move/delete only when 'tabs' is visible (not in ToolbarTab's settings)
                if tabs.isVisible():
                    if key == Qt.Key_Backspace or key == Qt.Key_Delete:
                        if buttonListWidget.hasFocus():
                            onButtonRemoveCommand()
                            return True
                    if key == Qt.Key_Up:
                        if buttonListWidget.hasFocus():
                            onButtonUp()
                            return True
                    if key == Qt.Key_Down:
                        if buttonListWidget.hasFocus():
                            onButtonDown()
                            return True

            if event.type() == QtCore.QEvent.KeyRelease:
                """ Handle tool shortcut in PieMenu """
                if state.app_state.flag_shortcut_override:
                    key = event.key()
                    try:
                        # if fast spinbox is open, we do nothing with shortcuts
                        if self.double_spinbox.isVisible():
                            pass
                    except:
                        # spinbox not show
                        try:
                            charKey = chr(key)
                        except:
                            charKey = ''

                        if charKey in state.app_state.list_shortcut_code:
                            self.menu.hide()
                            event.accept()
                            j = 0
                            for i in state.app_state.list_shortcut_code:
                                if i == charKey:
                                    # trigger tool shortcut action
                                    state.app_state.list_commands[j].trigger()
                                    state.app_state.flag_shortcut_override = False
                                    module = None
                                    event.accept()
                                    try:
                                        g = Gui.ActiveDocument.getInEdit()
                                        module = g.Module
                                        displaySpinBox = getParameterGlobal("Bool", "DisplaySpinBox")
                                        if (module is not None and module != 'SketcherGui') and displaySpinBox:
                                            PieMenuInstance.showAtMouseInstance()
                                    except:
                                        pass
                                j += 1
                            return True

                if self.menu.isVisible() and state.app_state.flag_shortcut_override:
                    key = event.key()
                    try:
                        # if fast spinbox is open, we do nothing with shortcuts
                        if self.double_spinbox.isVisible():
                            pass
                    except:
                        # spinbox not show
                        try:
                            charKey = chr(key)
                        except:
                            charKey = ''

                        if charKey in state.app_state.list_shortcut_code:
                            self.menu.hide()
                            event.accept()
                            j = 0
                            for i in state.app_state.list_shortcut_code:
                                if i == charKey:
                                    # trigger tool shortcut action
                                    state.app_state.list_commands[j].trigger()
                                    module = None
                                    event.accept()
                                    try:
                                        g = Gui.ActiveDocument.getInEdit()
                                        module = g.Module
                                        displaySpinBox = getParameterGlobal("Bool", "DisplaySpinBox")
                                        if (module is not None and module != 'SketcherGui') and displaySpinBox:
                                            PieMenuInstance.showAtMouseInstance()
                                    except:
                                        pass
                                j += 1
                            return True
                # run listTopo (context) when CTRL is release: allow multiple selection
                if event.type() == QtCore.QEvent.KeyRelease and event.key() == QtCore.Qt.Key_Control:
                    enableContext = config.get_params()["main"].GetBool("EnableContext")
                    if enableContext:
                        self.debounceTimer.start(100)
                        self.stop_filter()
                        listTopo()

            elif event.type() == QtCore.QEvent.Wheel:
                """ Press CTRL + rotate Wheel = X10, Press SHIFT + rotate Wheel = X0.1, Press CTRL+SHIFT + rotate Wheel= X0.01 """
                modifiers = event.modifiers()
                if modifiers & QtCore.Qt.ControlModifier and modifiers & QtCore.Qt.ShiftModifier:
                    # NOTE: weird behavior, you have to set 0.001 to modify the hundredths...
                    step = 0.001
                elif modifiers & QtCore.Qt.ShiftModifier:
                    step = 0.1
                else:
                    step = 1.0
                try:
                    self.double_spinbox.setProperty("singleStep", step)
                except:
                    None
            """ Filtrer les événements pour détecter la minimisation """
            if obj == self.mw and event.type() == QtCore.QEvent.WindowStateChange:
                # Vérifier si la fenêtre principale est minimisée
                if self.mw.isMinimized():
                    self.menu.hide()
            return False

        def add_commands(self, commands, context=False, keyValue=None):
            """ Add commands to mieMenus """
            if state.app_state.first_load:
                # Load the needed workbenches at the first launch
                updateIconsPieMenus()
                state.app_state.first_load = False

            styleCurrentTheme = getStyle()
            try:
                g = Gui.ActiveDocument.getInEdit()
                module = g.Module
                wb = Gui.activeWorkbench()
                wbName = wb.name()
            except:
                module = None

            for i in self.buttons:
                i.deleteLater()
            self.buttons = []
            group = ""

            if keyValue is not None:
                indexList = getIndexList()
                for i in indexList:
                    pie = getParamIndex(str(i))
                    if pie == keyValue:
                        group = config.get_params()["index"].GetGroup(str(i))
                    else:
                        pass
            elif context:
                group = getGroup(mode=2)
            else:
                group = getGroup(mode=1)

            if len(commands) == 0:
                commandNumber = 1
            else:
                commandNumber = len(commands)

            self.offset_x = 0
            self.offset_y = 0

            # defaults values
            valueRadius = 100
            valueButton = 32
            shape = "Pie"
            num_of_column = 4
            icon_spacing = 8
            command_per_circle = 5
            outer_commands = set()
            pack_outer = False
            pack_inner = False
            shortcutLabelSize = 8

            try:
                valueRadius = group.GetInt("Radius")
                valueButton = group.GetInt("Button")
                shape = getShape(keyValue)
                num_of_column = getParameterGroup(keyValue, "Int", "NumColumn")
                icon_spacing = getParameterGroup(
                    keyValue, "Int", "IconSpacing")
                command_per_circle = getParameterGroup(
                    keyValue, "Int", "CommandPerCircle")
                outer_commands = set(group.GetString("OuterToolList").split(".,."))
                pack_outer = group.GetBool("PackOuterIcons", False)
                pack_inner = group.GetBool("PackInnerIcons", False)
                shortcutLabelSize = getParameterGroup(
                    keyValue, "Int", "ShortcutLabelSize")
                ### Fix https://github.com/Grubuntu/PieMenu/issues/124
                if shortcutLabelSize < 6:
                    shortcutLabelSize = 6
            except:
                None

            number_of_circle = 1
            buttonSize = valueButton

            if config.get_params()["main"].GetBool("ToolBar") or keyValue == "toolBarTab":
                valueRadius = 100
                valueButton = 32
                shape = "Pie"
                outer_commands = set()
                pack_inner = False
                pack_outer = False

            if valueRadius:
                self.radius = valueRadius
            else:
                self.radius = 100

            if valueButton:
                self.buttonSize = valueButton
            else:
                self.buttonSize = 32

            buttonSize = self.buttonSize

            if num_of_column == 0:
                num_of_column = 1

            if icon_spacing < 0:
                icon_spacing = 0

            if command_per_circle < 1:
                command_per_circle = 5

            if shape == "Pie":
                if commandNumber == 1:
                    angle = 0
                else:
                    angle = 2 * math.pi / commandNumber
                angleStart = 3 * math.pi / 2 - angle

            elif shape == "RainbowUp":
                if commandNumber == 1:
                    angle = 0
                else:
                    angle = math.pi / (commandNumber-1)
                angleStart = 3 * math.pi / 2 - (angle*(commandNumber+1))/2

            elif shape == "RainbowDown":
                if commandNumber == 1:
                    angle = 0
                    buttonSize = self.buttonSize
                else:
                    angle = math.pi / (commandNumber-1)
                angleStart = math.pi / 2 - (angle*(commandNumber+1))/2

            elif shape == "Concentric" or shape == "Star":
                angle = 2 * math.pi / (command_per_circle)
                angleStart = 3 * math.pi / 2 - angle

            else:
                angle = 2 * math.pi / commandNumber
                angleStart = 3 * math.pi / 2 - angle

            radius = radiusSize(buttonSize)
            icon = iconSize(buttonSize)
            outer_flags = [command.objectName() in outer_commands for command in commands]
            outer_ring = shape == "Pie" and any(outer_flags)
            custom_ring_layout = shape == "Pie" and (outer_ring or pack_inner)
            ring_positions = outer_ring_positions(
                outer_flags, self.radius, buttonSize, icon, pack_outer, pack_inner
            ) if custom_ring_layout else []
            ring_radius = self.radius
            if outer_ring:
                ring_radius += buttonSize + icon * 0.6

            displayCommandName = False
            displayPreselect = False
            enableShortcut = False
            displayShortcut = False
            if shape in ["Pie", "LeftRight"]:
                try:  # get displayCommandName to display or not command name only for Pie shape
                    displayCommandName = getParameterGroup(
                        keyValue, "Bool", "DisplayCommand")
                except:
                    None
            if shape in ["Pie", "RainbowUp", "RainbowDown"]:
                try:  # get displayPreselect to display or not command name only for Pie shape
                    displayPreselect = getParameterGroup(
                        keyValue, "Bool", "DisplayPreselect")
                except:
                    None

            try:  # get enableShortcut to enable or not shortcut
                enableShortcut = getParameterGroup(
                    keyValue, "Bool", "EnableShorcut")
            except:
                None

            if custom_ring_layout:
                displayCommandName = False
                displayPreselect = False
            try:  # get displayShortcut to display or not shortcut
                displayShortcut = getParameterGroup(
                    keyValue, "Bool", "DisplayShorcut")
            except:
                None

            showPie = False
            # handle case when not in edit mode or if  Sketcher is open
            try:
                if (Gui.ActiveDocument.getInEdit() is None) or (module == 'SketcherGui') or (module == 'AssemblyGui'):
                    showPie = True
            except:
                None

            # handle case when there is any document open
            try:
                # if there is any open document we throw exception, to set showPie to True to show PieMenu
                App.ActiveDocument.Name
            except:
                showPie = True

            if showPie:
                num = 1

                ### for Pie shape with commands names ###
                ecart = (2 * self.radius) / ((commandNumber)/2)
                Y = -self.radius - ecart
                X = 0
                X_shortcut = 0
                Y_shortcut = 0

                ### 48 = code ascii pour le chiffre 0 ###
                shortcutCode = 48
                state.app_state.list_commands = []
                state.app_state.list_shortcut_code = []
                maxTextLength = 0
                for command_index, i in enumerate(commands):
                    """ show PieMenu in Edit Feature and in Sketcher """
                    button = HoverButton()
                    button.setParent(self.menu)
                    button.setObjectName("pieMenu")
                    button.setAttribute(QtCore.Qt.WA_Hover)
                    button.setStyleSheet(styleCurrentTheme + radius)
                    button.setDefaultAction(commands[commands.index(i)])
                    button.setIconSize(QtCore.QSize(icon, icon))
                    button.setGeometry(0, 0, buttonSize, buttonSize)

                    # Preselection Arrow
                    buttonPreselect = PreselectButton()

                    # modify style for display command name (only with Pie shape)
                    if displayCommandName and shape == "Pie":
                        # set minimum Y spacing at 1.2 * buttonSize
                        if ecart < (1.2 * buttonSize):
                            buttonSize = (ecart / 1.2)
                            radius = radiusSize(buttonSize)
                            icon = iconSize(buttonSize)

                        angle = (2 * math.pi) / (commandNumber)
                        button.setIcon(QtGui.QIcon())
                        # set padding and font size dependind on icon size
                        font_size = max(1, round(icon/2))

                        # get length of the string
                        text_length = QFontMetrics(button.font()).horizontalAdvance(
                            commands[commands.index(i)].text())

                        button.setGeometry(
                            buttonSize, 0,  2 * buttonSize + text_length, buttonSize)
                        # layout for icon and command string
                        layout = QtGui.QHBoxLayout(button)
                        layout.setContentsMargins((icon/4), 0, 0, 0)

                        iconButton = QtGui.QIcon(
                            commands[commands.index(i)].icon())
                        iconLabel = QtGui.QLabel()
                        iconLabel.setObjectName("iconLabel")
                        iconLabel.setPixmap(
                            iconButton.pixmap(QtCore.QSize(icon, icon)))
                        iconMarging = ""
                        # right side
                        if (num) <= (commandNumber/2):
                            padding = "QToolButton#pieMenu {padding-left: " + str(
                                icon) + "px; font-size: " + str(font_size) + "px;}"
                            Y += ecart
                            Y_shortcut = Y
                            if Y > self.radius:
                                Y = self.radius
                                Y_shortcut = Y
                            if num == 1:
                                X = 0
                                X_shortcut = 0
                                Y_shortcut = Y + icon
                            else:
                                X = self.radius * \
                                    (math.cos(angle * num + angleStart)) + \
                                    (buttonSize + text_length/2)
                                padding = "QToolButton#pieMenu {padding-left: " + str(
                                    icon) + "px; font-size: " + str(font_size) + "px;}"
                                X_shortcut = ((self.radius) * (math.cos(angle * num + angleStart)) + (
                                    buttonSize + text_length/2)) - (text_length/2 + 1.8*icon)
                                Y_shortcut = Y

                        # handle bottom right for odd commandNumber
                        elif (commandNumber % 2) == 1 and (num) == ((commandNumber+1)/2):
                            X = self.radius * \
                                (math.cos(angle * num + angleStart)) + \
                                (buttonSize + text_length/2)
                            Y = self.radius - ecart/2
                            X_shortcut = (self.radius * (math.cos(angle * num + angleStart)) + (
                                buttonSize + text_length/2)) - (text_length/2 + 1.8*icon)
                            Y_shortcut = Y

                        # handle bottom left for odd commandNumber
                        elif (commandNumber % 2) == 1 and (num) == (((commandNumber+1)/2)+1):
                            X = self.radius * \
                                (math.cos(angle * num + angleStart)) - \
                                (buttonSize + text_length/2)
                            Y = self.radius - ecart/2
                            layout.addStretch(1)
                            padding = "QToolButton#pieMenu {padding-right: " + str(icon) \
                                + "px; font-size: " + str(font_size) + "px;}"
                            iconMarging = "#iconLabel {margin-right: " + \
                                str(icon/4) + "px;}"
                            X_shortcut = (self.radius * (math.cos(angle * num + angleStart)) - (
                                buttonSize + text_length/2)) + (text_length/2 + 1.8*icon)
                            Y_shortcut = Y

                        # even commandNumber case, set the button on the middle bottom
                        elif (commandNumber % 2) == 0 and (num) == ((commandNumber/2)+1):
                            X = 0
                            Y = self.radius
                            X_shortcut = X
                            Y_shortcut = Y - icon

                        # left side
                        else:
                            Y -= ecart
                            if Y < -self.radius:
                                Y = -self.radius
                            X = self.radius * \
                                (math.cos(angle * num + angleStart)) - \
                                (buttonSize + text_length/2)
                            layout.addStretch(1)
                            padding = "QToolButton#pieMenu {padding-right: " + str(icon) \
                                + "px; font-size: " + str(font_size) + "px;}"
                            iconMarging = "#iconLabel {margin-right: " + \
                                str(icon/4) + "px;}"
                            X_shortcut = (self.radius * (math.cos(angle * num + angleStart)) - (
                                buttonSize + text_length/2)) + (text_length/2 + 1.8*icon)
                            Y_shortcut = Y

                        button.setProperty("ButtonX", X)
                        button.setProperty("ButtonY", Y)

                        buttonPreselect.setProperty("ButtonX", (self.radius - 1.2 * buttonSize) *
                                                    (math.cos(angle * num + angleStart)))
                        buttonPreselect.setProperty("ButtonY", (self.radius - 1.2 * buttonSize) *
                                                    (math.sin(angle * num + angleStart)))

                        iconLabel.setStyleSheet(
                            styleCurrentTheme + iconMarging)
                        button.setStyleSheet(
                            styleCurrentTheme + radius + padding)
                        layout.addWidget(iconLabel)

                        # self.menu size Pie shape + command name 
                        if text_length > maxTextLength:
                            maxTextLength = text_length
                        width =  valueRadius * 2 + buttonSize + 4 + 2 * maxTextLength + 3 * buttonSize
                        height = valueRadius * 2 + buttonSize + 4
                        self.menu.setFixedSize(width, height)

                    elif shape == "TableTop":
                        ### Table  Top ###
                        num_of_line = math.ceil(commandNumber/num_of_column)
                        offset = num_of_line * (buttonSize + icon_spacing)
                        X = ((num-1) % num_of_column) * \
                            (buttonSize + icon_spacing)
                        Y = self.radius / 2 + \
                            ((num-1) // num_of_column) * \
                            (buttonSize + icon_spacing)
                        button.setProperty(
                            "ButtonX", X - ((num_of_column-1) * (buttonSize + icon_spacing)) / 2)
                        button.setProperty("ButtonY", -Y)

                        X_shortcut = (
                            X - ((num_of_column-1) * (buttonSize + icon_spacing)) / 2) + icon/2
                        Y_shortcut = -Y + icon/2

                        # self.menu size Table Top
                        width = num_of_column * (buttonSize + icon_spacing)
                        height = valueRadius + offset + (buttonSize + icon_spacing) * (num_of_line - 1)
                        self.menu.setFixedSize(width, height)

                    elif shape == "TableDown":
                        ### Table Down  ###
                        num_of_line = math.ceil(commandNumber/num_of_column)
                        offset = num_of_line * (buttonSize + icon_spacing)
                        X = ((num-1) % num_of_column) * \
                            (buttonSize + icon_spacing)
                        Y = - buttonSize - self.radius / 4 - \
                            ((num-1) // num_of_column) * \
                            (buttonSize + icon_spacing)
                        button.setProperty(
                            "ButtonX", X - ((num_of_column-1) * (buttonSize + icon_spacing)) / 2)
                        button.setProperty("ButtonY", -Y)

                        X_shortcut = (
                            X - ((num_of_column-1) * (buttonSize + icon_spacing)) / 2) + icon/2
                        Y_shortcut = -Y - icon/2
                        
                        # self.menu size Table Down
                        width = num_of_column * (buttonSize + icon_spacing)
                        height = valueRadius + offset + (buttonSize + icon_spacing) * (num_of_line - 1)
                        self.menu.setFixedSize(width, height)

                    elif shape == "TableLeft":
                        ### Table Left  ###
                        num_of_line = math.ceil(commandNumber/num_of_column)
                        X = - buttonSize - self.radius / 2 - \
                            ((num-1) // num_of_column) * \
                            (buttonSize + icon_spacing)
                        Y = ((num-1) % num_of_column) * \
                            (buttonSize + icon_spacing)
                        button.setProperty("ButtonX", X)
                        button.setProperty(
                            "ButtonY", Y - ((num_of_column-1) * (buttonSize + icon_spacing)) / 2)

                        X_shortcut = X + icon/2
                        Y_shortcut = Y - \
                            ((num_of_column-1) * (buttonSize + icon_spacing)) / 2 + icon/2

                        # self.menu size Table Left
                        width = 2 * (valueRadius + num_of_line * (buttonSize + 4 + icon_spacing))
                        height = num_of_column * (icon_spacing + buttonSize + 4)
                        self.menu.setFixedSize(width, height)

                    elif shape == "TableRight":
                        ### Table Right  ###
                        num_of_line = math.ceil(commandNumber/num_of_column)
                        X = buttonSize + self.radius / 2 + \
                            ((num-1) // num_of_column) * \
                            (buttonSize + icon_spacing)
                        Y = ((num-1) % num_of_column) * \
                            (buttonSize + icon_spacing)
                        button.setProperty("ButtonX", X)
                        button.setProperty(
                            "ButtonY", Y - ((num_of_column-1) * (buttonSize + icon_spacing)) / 2)

                        X_shortcut = X - icon/2
                        Y_shortcut = Y - \
                            ((num_of_column-1) * (buttonSize + icon_spacing)) / 2 + icon/2
                            
                        # self.menu size Table Right
                        width = 2 * (valueRadius + num_of_line * (buttonSize + 4 + icon_spacing))
                        height = num_of_column * (icon_spacing + buttonSize + 4)
                        self.menu.setFixedSize(width, height)

                    elif shape == "UpDown":
                        ### Table Up and Down  ###
                        num_of_column = math.ceil(commandNumber / 2)
                        X = ((num - 1) % num_of_column) * \
                            (buttonSize + icon_spacing)
                        if ((num - 1) < num_of_column):
                            offset = 0
                            side = -1
                        else:
                            offset = 2 * self.radius
                            side = 1
                        Y = (self.radius - offset)

                        button.setProperty(
                            "ButtonX", X - ((num_of_column - 1) * (buttonSize + icon_spacing)) / 2)
                        button.setProperty("ButtonY", -Y)

                        X_shortcut = X - \
                            ((num_of_column - 1) *
                             (buttonSize + icon_spacing)) / 2 + icon/2
                        Y_shortcut = -Y - (side * icon/2)

                        # self.menu size Table Up and Down
                        width = num_of_column * (buttonSize + 4 + icon_spacing)
                        height = valueRadius * 2 + buttonSize + 4
                        self.menu.setFixedSize(width, height)

                    elif shape == "Concentric":
                        ### Concentric ###
                        button.setProperty("ButtonX", self.radius *
                                           (math.cos(angle * num + angleStart)))
                        button.setProperty("ButtonY", self.radius *
                                           (math.sin(angle * num + angleStart)))

                        X_shortcut = (self.radius) * \
                            (math.cos(angle * num + angleStart)) + icon/2
                        Y_shortcut = (self.radius) * \
                            (math.sin(angle * num + angleStart)) + icon/2

                        if ((num % command_per_circle) == 0):
                            num = 0
                            self.radius = self.radius + buttonSize + icon_spacing
                            number_of_circle = number_of_circle + 1
                            command_per_circle = command_per_circle + command_per_circle
                            angle = 2 * math.pi / command_per_circle
                            angleStart = angleStart + angle/2

                        # self.menu size Concentric
                        width =  self.radius * 2 + buttonSize + 4
                        height = self.radius * 2 + buttonSize + 4
                        self.menu.setFixedSize(width, height)

                    elif shape == "Star":
                        ### Star ###
                        button.setProperty("ButtonX", self.radius *
                                           (math.cos(angle * num + angleStart)))
                        button.setProperty("ButtonY", self.radius *
                                           (math.sin(angle * num + angleStart)))

                        X_shortcut = (self.radius) * \
                            (math.cos(angle * num + angleStart)) + icon/2
                        Y_shortcut = (self.radius) * \
                            (math.sin(angle * num + angleStart)) + icon/2

                        if ((num % command_per_circle) == 0):
                            self.radius = self.radius + buttonSize + icon_spacing

                        # self.menu size Star
                        width =  self.radius * 2 + icon_spacing + buttonSize
                        height = self.radius * 2 + icon_spacing + buttonSize
                        self.menu.setFixedSize(width, height)

                    elif shape == "LeftRight":
                        ### Left and Right with command names ###
                        if displayCommandName:
                            num_of_column = math.ceil(commandNumber/2)
                            button.setIcon(QtGui.QIcon())
                            # set padding and font size dependind on icon size
                            font_size = max(1, round(icon/2))
                            if ((num-1) < (num_of_column)):
                                # Left side icons
                                padding = "QToolButton#pieMenu {padding-right: " + str(icon) \
                                    + "px; font-size: " + \
                                    str(font_size) + "px;}"
                            else:
                                # Right side icons
                                padding = "QToolButton#pieMenu {padding-left: " + str(icon) \
                                    + "px; font-size: " + \
                                    str(font_size) + "px;}"
                            button.setStyleSheet(
                                styleCurrentTheme + radius + padding)
                            # get length of the string
                            text_length = QFontMetrics(button.font()).horizontalAdvance(
                                commands[commands.index(i)].text())

                            button.setGeometry(
                                buttonSize, 0,  2 * buttonSize + text_length, buttonSize)
                            # layout for icon and command string
                            layout = QtGui.QHBoxLayout(button)
                            layout.setContentsMargins((icon/4), 0, 0, 0)
                            if ((num-1) < (num_of_column)):
                                # Left side icons: align icon to the right and add some margin
                                layout.addStretch(1)
                                iconMarging = "#iconLabel {margin-right: " + \
                                    str(icon/4) + "px;}"

                            iconButton = QtGui.QIcon(
                                commands[commands.index(i)].icon())
                            iconLabel = QtGui.QLabel()
                            iconLabel.setObjectName("iconLabel")
                            iconLabel.setPixmap(
                                iconButton.pixmap(QtCore.QSize(icon, icon)))
                            if ((num-1) < (num_of_column)):
                                # Left side icons
                                iconLabel.setStyleSheet(
                                    styleCurrentTheme + iconMarging)
                            else:
                                # Right side icons
                                iconLabel.setStyleSheet(styleCurrentTheme)
                            layout.addWidget(iconLabel)
                            Y = ((num - 1) % num_of_column) * \
                                (buttonSize + icon_spacing)
                            if ((num-1) < (num_of_column)):
                                # Left side icons
                                offset = - text_length
                                side = -1
                            else:
                                # Right side icons
                                offset = 2 * self.radius
                                side = 1
                            # TODO: align them to the left
                            X = (self.radius - offset - text_length/2)

                            button.setProperty("ButtonX", -X)
                            button.setProperty(
                                "ButtonY", Y - ((num_of_column - 1) * (buttonSize + icon_spacing)) / 2)

                            X_shortcut = side * (self.radius - buttonSize)
                            Y_shortcut = Y - \
                                ((num_of_column - 1) *
                                 (buttonSize + icon_spacing)) / 2 + icon/2
                            # self.menu size Left and Right with command names
                            if text_length > maxTextLength:
                                maxTextLength = text_length
                            width = valueRadius * 2 + buttonSize + 4 + maxTextLength * 2 
                            height = valueRadius * 2 + buttonSize + 4 + icon_spacing * (commandNumber/2)
                            self.menu.setFixedSize(width, height)

                        else:
                            ### Left and Right  ###
                            num_of_column = math.ceil(commandNumber/2)
                            Y = ((num - 1) % num_of_column) * \
                                (buttonSize + icon_spacing)
                            if ((num-1) < (num_of_column)):
                                offset = 0
                                side = -1
                            else:
                                offset = 2*self.radius
                                side = 1
                            X = (self.radius - offset)

                            button.setProperty("ButtonX", -X)
                            button.setProperty(
                                "ButtonY", Y - ((num_of_column - 1) * (buttonSize + icon_spacing)) / 2)

                            X_shortcut = -X - (side * icon/2)
                            Y_shortcut = Y - \
                                ((num_of_column - 1) *
                                 (buttonSize + icon_spacing)) / 2 + icon/2
                                 
                            # self.menu size Left and Right without command names
                            width = valueRadius * 2 + buttonSize + 4 
                            height = valueRadius * 2 + buttonSize + 4 + icon_spacing * (commandNumber/2)
                            self.menu.setFixedSize(width, height)

                    else:
                        ### Pie without commands names / RainbowUp / RainbowDown   ###
                        if custom_ring_layout:
                            x, y = ring_positions[command_index]
                        else:
                            x = self.radius * math.cos(angle * num + angleStart)
                            y = self.radius * math.sin(angle * num + angleStart)
                        button.setProperty("ButtonX", x)
                        button.setProperty("ButtonY", y)

                        X_shortcut = x + icon/2
                        Y_shortcut = y + icon/2

                        buttonPreselect.setProperty(
                            "ButtonX", (self.radius - 1.2 * buttonSize) * (math.cos(angle * num + angleStart)))
                        buttonPreselect.setProperty(
                            "ButtonY", (self.radius - 1.2 * buttonSize) * (math.sin(angle * num + angleStart)))

                        # self.menu size Pie without commands names / RainbowUp / RainbowDown
                        width = (math.ceil(ring_radius * 2 + buttonSize + 4)
                                 if outer_ring else valueRadius * 2 + buttonSize + 4)
                        height = width
                        self.menu.setFixedSize(width, height)

                    if displayPreselect:
                        buttonPreselect.setParent(self.menu)
                        buttonPreselect.setObjectName("stylebuttonPreselect")
                        buttonPreselect.setAttribute(QtCore.Qt.WA_Hover)
                        buttonPreselect.setStyleSheet(styleCurrentTheme)
                        buttonPreselect.setDefaultAction(
                            commands[commands.index(i)])
                        buttonPreselect.setToolTip(None)

                        angle_total = angle * num + angleStart + math.pi*3/2
                        sizeRound = buttonSize * \
                            (abs(math.sin(angle_total)) +
                             abs(math.cos(angle_total)))

                        buttonPreselect.setIconSize(
                            QtCore.QSize(sizeRound, sizeRound))
                        rotation_angle = math.degrees(
                            angle * num + angleStart) + 270
                        buttonPreselect.originalPixmap = QtGui.QPixmap(
                            resources.iconArrowDown)
                        buttonPreselect.setGeometry(0, 0, sizeRound, sizeRound)

                        trans = QTransform()
                        trans.rotate(rotation_angle)
                        transformed_pixmap = buttonPreselect.originalPixmap.transformed(
                            trans)

                        blankIcon = QtGui.QPixmap(resources.iconBlank)
                        buttonPreselect.setIcon(QtGui.QIcon(blankIcon))
                        buttonPreselect.setBaseIcon(QtGui.QIcon(blankIcon))
                        buttonPreselect.setHoverIcon(
                            QtGui.QIcon(transformed_pixmap))

                        self.buttons.append(buttonPreselect)

                    self.buttons.append(button)

                    #### Manage Separator ###
                    if (commands[commands.index(i)].text()) == translate('PieMenuTab', 'Separator'):
                        button.setObjectName("styleSeparator")
                        button.setIcon(QtGui.QIcon(resources.iconSeparator))
                        iconButton = QtGui.QIcon(resources.iconSeparator)
                        buttonPreselect.setVisible(False)
                        try:
                            iconLabel.setPixmap(
                                iconButton.pixmap(QtCore.QSize(icon, icon)))
                        except:
                            None
                    else:
                        if enableShortcut:
                            if shortcutCode <= 90:
                                # Add button label for Shortcuts Tools on PieMenu
                                shortcutLabel = HoverButton()
                                shortcutLabel.setParent(self.menu)
                                shortcutLabel.setObjectName(
                                    "pieMenuShortcutTool")

                                fontSize = "QToolButton#pieMenuShortcutTool {font-size: " + str(
                                    shortcutLabelSize) + "px;}"

                                shortcutLabel.setStyleSheet(
                                    styleCurrentTheme + fontSize)
                                shortcutLabel.setDefaultAction(
                                    commands[commands.index(i)])
                                shortcutLabel.setToolButtonStyle(
                                    Qt.ToolButtonTextOnly)
                                shortcutLabel.setText(chr(shortcutCode))
                                shortcutLabel.setToolTip(None)

                                state.app_state.list_commands.append(
                                    commands[commands.index(i)])
                                state.app_state.list_shortcut_code.append(chr(shortcutCode))

                                if shortcutCode == 57:
                                    shortcutCode = 64
                                shortcutCode += 1
                                # trick to avoid X key which bug !
                                if shortcutCode == 88:
                                    shortcutCode = 89

                                shortcutLabel.setProperty(
                                    "ButtonX", X_shortcut)
                                shortcutLabel.setProperty(
                                    "ButtonY", Y_shortcut)

                                if displayShortcut:
                                    self.buttons.append(shortcutLabel)

                    num = num + 1

            displaySpinBox = getParameterGlobal("Bool", "DisplaySpinBox")
            buttonQuickMenu = quickMenu()
            if checkboxQuickMenu.isChecked():
                buttonQuickMenu.setParent(self.menu)
                self.buttons.append(buttonQuickMenu)
            else:
                buttonQuickMenu.hide()

            centerStart = len(self.buttons)
            try:
                if keyValue == "View" and (Gui.ActiveDocument.getInEdit() is None or (module == 'AssemblyGui')):
                    buttonClose = closeButton()
                    buttonClose.setParent(self.menu)
                    self.buttons.append(buttonClose)
            except:
                None

            try:
                if (Gui.ActiveDocument.getInEdit() is not None and not (module == 'AssemblyGui')):
                    """ or show Valid and Cancel buttons in Edit Feature Only """
                    buttonValid = self.validButton()
                    buttonValid.setStyleSheet(styleCurrentTheme)
                    buttonValid.setParent(self.menu)
                    buttonValid.clicked.connect(self.validation)
                    self.buttons.append(buttonValid)

                    buttonCancel = self.cancelButton()
                    buttonCancel.setStyleSheet(styleCurrentTheme)
                    buttonCancel.setParent(self.menu)
                    buttonCancel.clicked.connect(self.cancel)
                    self.buttons.append(buttonCancel)

                    if (module is not None and module != 'SketcherGui' and wbName == 'PartDesignWorkbench'):
                        """ Show Spinbox in Edit Feature in Part Design WB only """
                        layoutOptions = QtGui.QVBoxLayout()
                        fonctionActive = g.Object

                        self.double_spinbox = self.doubleSpinbox()
                        self.double_spinbox.setParent(self.menu)
                        self.double_spinbox.valueChanged.connect(
                            self.spin_interactif)
                        self.buttons.append(self.double_spinbox)
                        self.double_spinbox.setVisible(True)

                        def checkbox_layout(checkbox_func, ObjectAttribute="Type", ObjectType=True):
                            checkbox = checkbox_func()
                            checkbox.setParent(self.menu)
                            checkbox.setObjectName("styleCheckbox")
                            checkbox.setStyleSheet(styleCurrentTheme)
                            checkbox.setMinimumWidth(220)
                            checkbox.stateChanged.connect(self.spin_interactif)

                            self.buttons.append(checkbox)

                            if getattr(g.Object, ObjectAttribute) == ObjectType:
                                checkbox.setChecked(True)
                            else:
                                checkbox.setChecked(False)
                            self.checkbox = checkbox
                            return self.checkbox

                        layoutMidPlane = QHBoxLayout()
                        layoutReversed = QHBoxLayout()
                        layoutThroughAll = QHBoxLayout()

                        if (str(fonctionActive) == '<PartDesign::Fillet>'):
                            Gui.ExpressionBinding(self.double_spinbox).bind(
                                g.Object, "Radius")
                            quantity = Units.Quantity(Units.Quantity(
                                g.Object.Radius).getUserPreferred()[0])

                        elif (str(fonctionActive) == '<PartDesign::Chamfer>'):
                            Gui.ExpressionBinding(
                                self.double_spinbox).bind(g.Object, "Size")
                            quantity = Units.Quantity(Units.Quantity(
                                g.Object.Size).getUserPreferred()[0])

                        elif (str(fonctionActive) == '<PartDesign::Thickness>'):
                            Gui.ExpressionBinding(
                                self.double_spinbox).bind(g.Object, "Value")
                            quantity = Units.Quantity(Units.Quantity(
                                g.Object.Value).getUserPreferred()[0])

                        elif (str(fonctionActive) == '<PartDesign::Pad>') or (str(fonctionActive) == '<PartDesign::Pocket>'):
                            Gui.ExpressionBinding(self.double_spinbox).bind(
                                g.Object, "Length")
                            quantity = Units.Quantity(Units.Quantity(
                                g.Object.Length).getUserPreferred()[0])

                            self.checkbox_midPlane = checkbox_layout(
                                self.checkboxSymToPlane, "Midplane", True)
                            layoutMidPlane.addWidget(self.checkbox_midPlane)
                            layoutOptions.addLayout(layoutMidPlane)

                            self.checkbox_reversed = checkbox_layout(
                                self.checkboxReversed, "Reversed", True)
                            layoutReversed.addWidget(self.checkbox_reversed)
                            layoutOptions.addLayout(layoutReversed)

                            if (str(fonctionActive) == '<PartDesign::Pocket>'):
                                self.checkbox_throughAll = checkbox_layout(
                                    self.checkboxThroughAll, "Type", "ThroughAll")

                                layoutThroughAll.addWidget(
                                    self.checkbox_throughAll)
                                layoutOptions.addLayout(layoutThroughAll)

                        elif (str(fonctionActive) == '<PartDesign::Revolution>') or (str(fonctionActive) == '<PartDesign::Groove>'):
                            Gui.ExpressionBinding(
                                self.double_spinbox).bind(g.Object, "Angle")
                            quantity = Units.Quantity(Units.Quantity(
                                g.Object.Angle).getUserPreferred()[0])

                            self.checkbox_midPlane = checkbox_layout(
                                self.checkboxSymToPlane, "Midplane", True)
                            layoutMidPlane.addWidget(self.checkbox_midPlane)
                            layoutOptions.addLayout(layoutMidPlane)

                            self.checkbox_reversed = checkbox_layout(
                                self.checkboxReversed, "Reversed", True)
                            layoutReversed.addWidget(self.checkbox_reversed)
                            layoutOptions.addLayout(layoutReversed)

                        self.double_spinbox.setProperty('value', quantity)

                        self.double_spinbox.setFocus()
                        self.double_spinbox.selectAll()

                        self.offset_x = 10
                        self.offset_y = 28
            except:
                None

            # Accept/cancel controls and feature inputs take priority over settings.
            if keyValue != "View" and len(self.buttons) == centerStart:
                self.buttons.append(self.settingsButton(keyValue))

            if compositingManager:
                pass
            else:
                for i in self.buttons:
                    i.setAttribute(QtCore.Qt.WA_PaintOnScreen)

        def hide(self):
            for i in self.buttons:
                i.hide()
            self.menu.hide()

        def showAtMouseInstance(self, keyValue=None):
            nonlocal contextPhase
            enableContext = config.get_params()["main"].GetBool("EnableContext")

            if contextPhase:
                if not keyValue:
                    sel = Gui.Selection.getSelectionEx()
                    if not sel:
                        self.hide()
                        contextPhase = False
                        updateCommands()
                    elif not enableContext:
                        self.hide()
                        updateCommands()
                    else:
                        keyValue = getParam("ContextPie")
                        updateCommands(keyValue, context=True)
                else:
                    updateCommands(keyValue)
            else:
                updateCommands(keyValue)

            height = self.menu.height()
            width = self.menu.width()
            posX = width / 2
            posY = height / 2

            if windowShadow:
                pos = mw.mapFromGlobal(QtGui.QCursor.pos())
                cursor_pos = QtGui.QCursor.pos()
                self.menu.move(cursor_pos.x() - self.menu.width() // 2,
                               cursor_pos.y() - self.menu.height() // 2)

                self.menu.show()
                for i in self.buttons:
                    i.move(i.property("ButtonX") + posX - i.width() / 2 + self.offset_x,
                           i.property("ButtonY") + posY - i.height() / 2 + self.offset_y)
                    i.setVisible(True)
                    i.setParent(self.menu)
                    i.repaint()
            else:
                #### a vérifier ####
                pos = QtGui.QCursor.pos()
                x = int(pos.x() - self.menuSize / 2)
                y = int(pos.y() - self.menuSize / 2)
                self.menu.show()

                for i in self.buttons:
                    i.move(int(i.property("ButtonX") + (self.menuSize - i.size().width()) / 2 + self.offset_x),
                           int(i.property("ButtonY") + (self.menuSize - i.size().height()) / 2 + self.offset_y))
                    i.setVisible(True)


        def showPiemenuPreview(self, keyValue=None):
            """ Preview of PieMenu in widgetTable on Preferences Tab """
            # get BackgroundColor value in parameters, if 0 then we have a fresh install
            backgroundColorConfig = config.get_params()["color"].GetUnsigned(
                "BackgroundColor")
            cssColorTop = getCssColor(config.get_params()["color"], "BackgroundColor2")
            cssColorBottom = getCssColor(config.get_params()["color"], "BackgroundColor3")
            gradient = True
            useBackgroundColorMid = False

            if backgroundColorConfig != 0:
                gradient = config.get_params()["color"].GetBool("Gradient")
                radialGradient = config.get_params()["color"].GetBool("RadialGradient")
                useBackgroundColorMid = config.get_params()["color"].GetBool(
                    "UseBackgroundColorMid")
                cssColorSimple = getCssColor(config.get_params()["color"], "BackgroundColor")
                cssColorMiddle = getCssColor(config.get_params()["color"], "BackgroundColor4")

            if gradient:
                if useBackgroundColorMid:
                    showPreviewWidget.setStyleSheet(
                        f"background-color: qlineargradient(y1: 0, y2: 1, stop: 0 {cssColorTop}, stop: 0.5 {cssColorMiddle}, stop: 1 {cssColorBottom});")
                else:
                    showPreviewWidget.setStyleSheet(
                        f"background-color: qlineargradient(y1: 0, y2: 1, stop: 0 {cssColorTop}, stop: 1 {cssColorBottom})")

            elif radialGradient:
                if useBackgroundColorMid:
                    showPreviewWidget.setStyleSheet(
                        f"background-color: qradialgradient(cx: 0.5, cy: 0.5, radius: 0.5, fx: 0.5, fy: 0.5, stop: 0 {cssColorTop}, stop: 0.5 {cssColorMiddle}, stop: 1 {cssColorBottom});")
                else:
                    showPreviewWidget.setStyleSheet(
                        f"background-color: qradialgradient(cx: 0.5, cy: 0.5, radius: 0.5, fx: 0.5, fy: 0.5, stop: 0 {cssColorTop}, stop: 1 {cssColorBottom});")
            else:
                # color simple :
                showPreviewWidget.setStyleSheet(
                    f"background-color: {cssColorSimple};")

            shape = getParameterGroup(cBox.currentText(), "String", "Shape")

            # positions of PieMenu in widget
            height = showPiemenu.height()
            width = showPiemenu.width()
            posX = width / 2
            posY = height / 2

            if shape == "TableLeft":
                posX = width * 4 / 5

            if shape == "TableRight":
                posX = width / 5

            updateCommands(keyValue)

            if windowShadow:
                # needed for tools shortcut
                # To avoid flickering in PieMenuDialog window
                if pieMenuDialog.isVisible():
                    self.menu.setParent(pieMenuDialog)
                    self.menu.show()
                    self.menu.hide()
                    self.menu.setParent(None)

                for i in self.buttons:
                    i.move(i.property("ButtonX") + posX - i.width() / 2 + self.offset_x,
                           i.property("ButtonY") + posY - i.height() / 2 + self.offset_y)
                    i.setVisible(True)
                    i.setAttribute(Qt.WA_Disabled, True)
                    i.setParent(showPiemenu)
                    # disable quickMenu and (central) 
                    if i.objectName() == "styleButtonMenu" or i.objectName() == "styleMenuClose":
                        i.setEnabled(False)

            else:
                for i in self.buttons:
                    i.move(i.property("ButtonX")
                           + (self.menuSize - i.size().width()) /
                           2 + self.offset_x,
                           i.property("ButtonY")
                           + (self.menuSize - i.size().height()) / 2 + self.offset_y)
                    i.setVisible(True)
                    i.setAttribute(Qt.WA_Disabled, True)
                    i.setParent(showPiemenu)

                    # disable quickMenu and (central) 
                    if i.objectName() == "styleButtonMenu" or i.objectName() == "styleMenuClose":
                        i.setEnabled(False)


        def spin_interactif(self):
            """ Handle spinbox in fast edit mode """
            docName = App.ActiveDocument.Name
            g = Gui.ActiveDocument.getInEdit()
            fonctionActive = g.Object
            featureName = g.Object.Name

            size = self.double_spinbox.property('value')

            featureThroughAll = 0
            featureReversed = 0
            featureSymToPlane = 0

            try:
                featureThroughAll = self.checkbox_throughAll.isChecked()
            except:
                None

            try:
                featureReversed = self.checkbox_reversed.isChecked()
            except:
                None

            try:
                featureSymToPlane = self.checkbox_midPlane.isChecked()
            except:
                None

            if (str(fonctionActive) == '<PartDesign::Fillet>'):
                App.getDocument(docName).getObject(featureName).Radius = size
            elif (str(fonctionActive) == '<PartDesign::Chamfer>'):
                App.getDocument(docName).getObject(featureName).Size = size

            elif (str(fonctionActive) == '<PartDesign::Pocket>') or (str(fonctionActive) == '<PartDesign::Pad>')\
                    or (str(fonctionActive) == '<PartDesign::Revolution>') or (str(fonctionActive) == '<PartDesign::Groove>'):

                # reversed
                if featureReversed:
                    App.getDocument(docName).getObject(
                        featureName).Reversed = 1
                else:
                    App.getDocument(docName).getObject(
                        featureName).Reversed = 0

                # midplane
                fc_version = App.Version()[0:3]  # ex: ['1', '0', '2']
                major = int(fc_version[0])
                minor = int(fc_version[1])
                patch = int(fc_version[2])

                if featureSymToPlane:
                    if (major, minor, patch) <= (1, 0, 2):
                        # code valide pour les versions Freecad inférieures ou égale à 1.02
                        App.getDocument(docName).getObject(
                        featureName).Midplane = 1
                    else:
                        # code valide pour les versions Freecad supérieures à 1.02
                        App.getDocument(docName).getObject(
                        featureName).SideType = 2
                else:
                    if (major, minor, patch) <= (1, 0, 2):
                        # code valide pour les versions Freecad inférieures ou égale à 1.02
                        App.getDocument(docName).getObject(
                            featureName).Midplane = 0                    
                    else:
                        # code valide pour les versions Freecad supérieures à 1.02
                        App.getDocument(docName).getObject(
                            featureName).SideType = 0

                if (str(fonctionActive) == '<PartDesign::Pocket>'):
                    # through all
                    if featureThroughAll:
                        self.double_spinbox.setEnabled(False)
                        App.getDocument(docName).getObject(
                            featureName).Type = 1
                    else:
                        self.double_spinbox.setEnabled(True)
                        App.getDocument(docName).getObject(
                            featureName).Type = 0
                        App.getDocument(docName).getObject(
                            featureName).Length = size

                elif (str(fonctionActive) == '<PartDesign::Revolution>') or (str(fonctionActive) == '<PartDesign::Groove>'):
                    App.getDocument(docName).getObject(
                        featureName).Angle = size
                else:
                    App.getDocument(docName).getObject(
                        featureName).Length = size

            elif (str(fonctionActive) == '<PartDesign::Thickness>'):
                App.getDocument(docName).getObject(featureName).Value = size

            elif (str(fonctionActive) == '<PartDesign::Hole>'):
                self.double_spinbox.setVisible(False)
            else:
                self.double_spinbox.setVisible(False)

            App.ActiveDocument.recompute()
    #### END Class PieMenu ####

    class PieMenuDialog(QDialog):
        mw = Gui.getMainWindow()
        """ Class to handle PieMenuDialog events """

        def __init__(self, parent=None):

            super(PieMenuDialog, self).__init__(parent)

            self.setObjectName("PieMenuPreferences")
            self.setWindowTitle("PieMenu " + PIE_MENU_VERSION)
            self.closeEvent = self.customCloseEvent
            self.setWindowIcon(QtGui.QIcon(resources.iconPieMenuLogo))
            self.setMinimumSize(1000, 680)
            self.setModal(True)

        def customCloseEvent(self, event):
            # Caught close event to save parameters on disk
            App.saveParameter()
            onBackToSettings()
            window_icons.close()
            super(PieMenuDialog, self).closeEvent(event)

    #### END Classes definitions ####

    ### BEGIN Functions Def ####
    def getParamIndex(name):
        """ Get parameter from User parameter:BaseApp/PieMenu/Index """
        try:
            value = config.get_params()["index"].GetString(name).decode("UTF-8")
        except AttributeError:
            value = config.get_params()["index"].GetString(name)
        return value

    def getParam(name):
        """ Get parameter from User parameter:BaseApp/PieMenu """
        try:
            value = config.get_params()["main"].GetString(name).decode("UTF-8")
        except AttributeError:
            value = config.get_params()["main"].GetString(name)
        return value

    class PieMenuSettingsCommand:
        """ Command opening the PieMenu preferences dialog """

        def GetResources(self):
            """Return a dictionary with data that will be used by the button or menu item."""
            return {'MenuText': translate("AccesoriesMenu", "PieMenu"),
                    'ToolTip': translate("AccesoriesMenu", "Open PieMenu settings")}

        def Activated(self):
            """Run the following code when the command is activated (button press)."""
            onControl()

        def IsActive(self):
            """Return True when the command should be active or False when it should be disabled (greyed)."""
            return True

    class PieMenuWorkbenchManipulator:
        """ Workbench manipulator appending the PieMenu settings entry to the Edit menu """

        def modifyMenuBar(self):
            """Append a separator and the PieMenu settings command after the last item of the Edit menu."""
            return [
                {"append": "Separator", "menuItem": "Std_DlgPreferences"},
                {"append": "PieMenu_Settings", "menuItem": "Std_DlgPreferences"},
            ]

    def addEditMenuEntry():
        """Add the PieMenu settings command to the Edit menu once the main window is ready."""
        if mw.property("eventLoop"):
            mainWindowReady = False
            try:
                mw.mainWindowClosed
                mw.workbenchActivated
                mainWindowReady = True
            except AttributeError:
                pass
            if mainWindowReady:
                t.stop()
                t.deleteLater()

                Gui.addCommand("PieMenu_Settings", PieMenuSettingsCommand())
                if not getattr(Gui, "PieMenuWorkbenchManipulator", None):
                    Gui.PieMenuWorkbenchManipulator = PieMenuWorkbenchManipulator()
                    Gui.addWorkbenchManipulator(Gui.PieMenuWorkbenchManipulator)
                # rebuild the active workbench menu so the entry is shown now
                workbench = Gui.activeWorkbench()
                if workbench is not None:
                    workbench.reloadActive()

    def getCssColor(user_parameter, key):
        """ Return hex color to rgb format """
        color = user_parameter.GetUnsigned(key)
        hex_color = hex(color)[2:].zfill(8)
        rgb_hex_color = hex_color[:6]
        return f"#{rgb_hex_color}"

    def getStyle():
        """ Get style in parmaters """
        theme = config.get_params()["main"].GetString("Theme")
        if theme == "":
            theme = "Legacy"  # default theme if new installation
        stylesheet_path = f"{os.path.join(resources.stylepath, theme)}.qss"
        if not os.path.exists(stylesheet_path):
            stylesheet_path = f"{os.path.join(resources.stylepath, 'Legacy.qss')}"
            config.get_params()["main"].SetString("Theme", "Legacy")

        with open(stylesheet_path, "r") as f:
            styleCurrentTheme = f.read()
        qssPath = resources.stylepath + "\\"
        styleCurrentTheme = styleCurrentTheme.replace(
            "pieMenuQss:", qssPath.replace("\\", "/"))

        # Get FreeCAD ThemeAccentColors
        ThemeAccentColor1_hex = getCssColor(
            config.get_params()["accents"], "ThemeAccentColor1")
        ThemeAccentColor2_hex = getCssColor(
            config.get_params()["accents"], "ThemeAccentColor2")
        ThemeAccentColor3_hex = getCssColor(
            config.get_params()["accents"], "ThemeAccentColor3")
        styleCurrentTheme = styleCurrentTheme.replace(
            "@ThemeAccentColor1", str(ThemeAccentColor1_hex))
        styleCurrentTheme = styleCurrentTheme.replace(
            "@ThemeAccentColor2", str(ThemeAccentColor2_hex))
        styleCurrentTheme = styleCurrentTheme.replace(
            "@ThemeAccentColor3", str(ThemeAccentColor3_hex))
        return styleCurrentTheme

    def getParameterGlobal(paramType="String", paramName=""):
        """Get parameter from user parameters."""
        if paramType == "String":
            parameter = config.get_params()["main"].GetString(paramName)
        elif paramType == "Int":
            parameter = config.get_params()["main"].GetInt(paramName)
        elif paramType == "Bool":
            parameter = config.get_params()["main"].GetBool(paramName)
        else:
            pass
        return parameter

    def getParameterGroup(keyValue=None, paramType="String", paramName=""):
        """ Get parameter in settings, paramType = "String", "Int", "Bool" """
        parameter = ""

        if keyValue is None:
            keyValue = getParam("CurrentPie")
        indexList = getIndexList()
        for i in indexList:
            pieName = getParamIndex(str(i))
            if pieName == keyValue:
                param = config.get_params()["index"].GetGroup(str(i))
                if paramType == "String":
                    parameter = param.GetString(paramName)
                elif paramType == "Int":
                    parameter = param.GetInt(paramName)
                elif paramType == "Bool":
                    parameter = param.GetBool(paramName)
                else:
                    pass
        return parameter

    def setParameterGroup(keyValue=None, paramType="String", paramName="", paramValue=None):
        """ Set parameter in settings, paramType = "String", "Int", "Bool" """
        indexList = getIndexList()
        for i in indexList:
            pieName = getParamIndex(str(i))
            if pieName == keyValue:
                param = config.get_params()["index"].GetGroup(str(i))
                if paramType == "String":
                    param.SetString(paramName, paramValue)
                elif paramType == "Int":
                    param.SetInt(paramName, paramValue)
                elif paramType == "Bool":
                    param.SetBool(paramName, paramValue)
                else:
                    pass

    def getIndexList():
        """Get current pieMenus using available index (de-duplicated, order preserved)."""
        indexParam = config.get_params()["index"]
        rawIndexList = indexParam.GetString("IndexList")
        if rawIndexList:
            rawIndexList = list(map(int, rawIndexList.split(".,.")))
        else:
            rawIndexList = []

        indexList = []
        for i in rawIndexList:
            if i not in indexList:
                indexList.append(i)

        if indexList != rawIndexList:
            indexParam.SetString(
                "IndexList", ".,.".join(str(i) for i in indexList))

        return indexList

    #Qt6
    def getShortcutList():
        """Get keyboard shortcut and namePie from user parameters"""

        # Supprimer les anciens QShortcut
        for shortcut in mw.findChildren(QShortcut):
            try:
                shortcut.activated.disconnect()
            except Exception:
                pass
            shortcut.setParent(None)
            shortcut.deleteLater()

        shortcutList = []

        indexList = getIndexList()
        for i in indexList:
            param = config.get_params()["index"].GetGroup(str(i))
            namePie = config.get_params()["index"].GetString(str(i))
            shortcutKey = param.GetString("ShortcutKey")
            if shortcutKey:
                shortcutList.append(
                    (namePie, shortcutKey, param.GetString("DefaultWorkbench")))

        def create_shortcut_handler(name):
            return lambda: PieMenuInstance.showAtMouseInstance(keyValue=name)

        def create_workbench_handler(workbenchPies):
            def handler():
                active = Gui.activeWorkbench()
                wbName = active.name().replace("Workbench", "")
                namePie = workbenchPies.get(wbName)
                if namePie:
                    PieMenuInstance.showAtMouseInstance(keyValue=namePie)
            return handler

        # The global shortcut owns its key; a per-pie shortcut must not be
        # bound on top of it (Qt would cycle between the colliding actions).
        usedShortcuts = set()
        if state.app_state.global_shortcut_key:
            usedShortcuts.add(
                QKeySequence(state.app_state.global_shortcut_key).toString())

        # Group the per-pie shortcuts by key, keeping the config order.
        keyOrder = []
        keyToPies = {}
        for namePie, shortcutKey, defaultWorkbench in shortcutList:
            keyString = QKeySequence(shortcutKey).toString()
            if not keyString or keyString in usedShortcuts:
                continue
            if keyString not in keyToPies:
                keyToPies[keyString] = []
                keyOrder.append(keyString)
            keyToPies[keyString].append((namePie, defaultWorkbench))

        for keyString in keyOrder:
            pies = keyToPies[keyString]
            workbenchPies = {}
            hasPieWithoutWorkbench = False
            for namePie, defaultWorkbench in pies:
                if defaultWorkbench and defaultWorkbench != "None":
                    workbenchPies[defaultWorkbench] = namePie
                else:
                    hasPieWithoutWorkbench = True

            shortcut = QShortcut(QKeySequence(keyString), mw)
            # A key shared by several workbench-associated pies (and by no pie
            # without an association) opens the pie matching the active
            # workbench, like the global shortcut, instead of only the first.
            if len(pies) > 1 and not hasPieWithoutWorkbench \
                    and len(workbenchPies) == len(pies):
                shortcut.activated.connect(
                    create_workbench_handler(workbenchPies))
            else:
                shortcut.activated.connect(
                    create_shortcut_handler(pies[0][0]))
            shortcut.setEnabled(True)

        # Retourner la liste affichable pour le debug ou l'affichage
        return [f"PieMenu_{name} => {key}" for name, key, wb in shortcutList]

    def setTriggerMode(triggerMode):
        """ Set TriggerMode in parameter """
        if triggerMode == "Press":
            spinHoverDelay.setEnabled(False)
        else:
            spinHoverDelay.setEnabled(True)
        indexList = getIndexList()
        for i in indexList:
            pieName = getParamIndex(str(i))
            if pieName == cBox.currentText():
                param = config.get_params()["index"].GetGroup(str(i))
                param.SetString("TriggerMode", triggerMode)

    def setGlobalKeyToggle():
        """ Set globlal key toggle mode in parameters """
        globalKeyToggle = checkboxGlobalKeyToggle.isChecked()
        config.get_params()["main"].SetBool("GlobalKeyToggle", globalKeyToggle)
        actionKey.setEnabled(True)

    def reloadWorkbench():
        try:
            wb = Gui.activeWorkbench()
            # needed to change WB and reload it : do only Gui.reloadWorkbench() is not enough
            Gui.activateWorkbench('PartDesignWorkbench')
            Gui.activateWorkbench('PartWorkbench')
            Gui.activateWorkbench(wb.name())
            Gui.updateGui()
        except:
            pass

    #
    # Code left on purpose, we should let it up to the user if they want to create shortcuts
    #
    # def createNestedPieMenus():
    #     """ Create a freeCAD command in order to use it as PieMenu """
    #     indexList = getIndexList()
    #     for i in indexList:
    #         pie = getParamIndex(str(i))
    #         iconPath = getParameterGroup(pie, "String", "IconPath")
    #         if iconPath == "":
    #             iconPath = resources.iconPieMenuLogo
    #
    #         Gui.addCommand('PieMenu_' + pie, NestedPieMenu(pie, iconPath))
    #
    #         globaltoolbar = App.ParamGet(
    #             'User parameter:BaseApp/Workbench/Global/Toolbar/Custom_PieMenu')
    #
    #         pieMenuTB = globaltoolbar.GetString('Name')
    #         if pieMenuTB == 'PieMenuTB':
    #             pass
    #         else:
    #             globaltoolbar.SetString('Name', 'PieMenuTB')
    #
    #         globaltoolbar.SetString('PieMenu_' + pie, 'FreeCAD')

    def updateIconsPieMenus():
        """ Update PieMenu icon after change it """
        indexList = getIndexList()
        lastWorkbench = Gui.activeWorkbench()
        workbenches = Gui.listWorkbenches()
        global loadedWorkbenches

        for i in indexList:
            pie = getParamIndex(str(i))
            iconPath = getParameterGroup(pie, "String", "IconPath")
            if iconPath == "":
                iconPath = resources.iconPieMenuLogo
            icon = getIconPieMenu(iconPath)
            namePie = 'PieMenu_' + pie

            try:
                workbench = extractWorkbench(icon)
                wbName = constants.workbench_map.get(workbench, workbench + "Workbench")
                if wbName in workbenches and wbName not in loadedWorkbenches:
                    message = translate(
                        "MainWindow",
                        "PieMenu needs to load {} to access icon resources. To avoid this message, please consider enabling auto-load for this workbench in FreeCAD's settings.",
                    ).format(wbName)
                    QtGui.QMessageBox.information(
                        None,
                        translate("MainWindow", "Workbench Loading"),
                        message,
                        QtGui.QMessageBox.Ok,
                    )

                    Gui.activateWorkbench(wbName)
                    loadedWorkbenches.append(wbName)
                    Gui.activateWorkbench(lastWorkbench.__class__.__name__)
            except:
                None

            all_actions = Gui.getMainWindow().findChildren(QtGui.QAction)

            for action in all_actions:
                if action.data() == iconPath:
                    icon = action.icon()
            for action in all_actions:
                if action.data() == namePie:
                    action.setIcon(QtGui.QIcon(icon))

    def onListToolBar():
        """Handle the toolbar list."""
        listToolBar.clear()
        listToolBar.blockSignals(True)
        if config.get_params()["main"].GetBool("ToolBar"):
            text = config.get_params()["main"].GetString("ToolBar")
            if ": " in text:
                toolbar_desc = text.split(": ")
                text = toolbar_desc[1]
        else:
            text = None

        for toolbar in mw.findChildren(QtGui.QToolBar):
            barList = []

            for action in toolbar.findChildren(QtGui.QAction):
                if not action.isSeparator() and action.text() != "":
                    barList.append(action)

            for command in barList:
                item = QListWidgetItem()
                item.setText(command.text())

                # filter for empty toolbar
                commands = []
                getGuiToolButtonData(command.text(), None, commands, None)
                if len(commands) != 0:
                    listToolBar.addItem(item)

        listToolBar.blockSignals(False)
        return listToolBar

    def radiusSize(buttonSize):
        """Calculates border radius for QToolButton based on the given buttonSize."""
        radius = str(math.trunc(buttonSize / 2))
        return "QToolButton {border-radius: " + radius + "px}"

    def iconSize(buttonSize):
        """Calculates the size of an icon based on the given buttonSize."""
        icon = buttonSize / 3 * 2
        return icon

    def closeButton(buttonSize=32):
        """Style the close button."""
        icon = iconSize(buttonSize)
        radius = radiusSize(buttonSize)
        button = QtGui.QToolButton()
        button.setObjectName("styleMenuClose")
        button.setProperty("ButtonX", 0)  # +, right
        button.setProperty("ButtonY", 0)  # +, down
        button.setGeometry(0, 0, buttonSize, buttonSize)
        button.setIconSize(QtCore.QSize(icon, icon))
        styleCurrentTheme = getStyle()
        button.setStyleSheet(styleCurrentTheme + radius)
        button.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        def onButton():
            PieMenuInstance.hide()

        button.clicked.connect(onButton)

        return button

    def contextList():
        state.app_state.context_all.clear()
        indexList = getIndexList()
        j = 0
        for i in indexList:
            group = config.get_params()["index"].GetGroup(str(i))
            for groupe in group.GetGroups():
                groupContext = group.GetGroup(groupe)
                if groupContext.GetBool("Enabled"):
                    current = {}
                    current["Index"] = str(i)
                    current["VertexSign"] = groupContext.GetString(
                        "VertexSign")
                    current["VertexValue"] = groupContext.GetInt("VertexValue")

                    current["EdgeSign"] = groupContext.GetString("EdgeSign")
                    current["EdgeValue"] = groupContext.GetInt("EdgeValue")

                    current["FaceSign"] = groupContext.GetString("FaceSign")
                    current["FaceValue"] = groupContext.GetInt("FaceValue")

                    current["ObjectSign"] = groupContext.GetString(
                        "ObjectSign")
                    current["ObjectValue"] = groupContext.GetInt("ObjectValue")
                    
                    current["AxisSign"] = groupContext.GetString("AxisSign")
                    current["AxisValue"] = groupContext.GetInt("AxisValue")

                    current["PlaneSign"] = groupContext.GetString(
                        "PlaneSign")
                    current["PlaneValue"] = groupContext.GetInt("PlaneValue")
                    state.app_state.context_all[j] = current
                    j += 1
                else:
                    pass

    def getContextPie(v, e, f, o, a, p):
        global globalContextPie
        global globalIndexPie
        global indexPie
        globalContextPie = False
        globalIndexPie = None
        indexPie = None
        for i in state.app_state.context_all:
            current = state.app_state.context_all[i]
            def vertex():
                if sign[current["VertexSign"]](v, current["VertexValue"]):
                    edge()
                else:
                    pass

            def edge():
                if sign[current["EdgeSign"]](e, current["EdgeValue"]):
                    face()
                else:
                    pass

            def face():
                if sign[current["FaceSign"]](f, current["FaceValue"]):
                    axis()
                else:
                    pass

            def axis():
                try:
                    if sign[current["AxisSign"]](a, current["AxisValue"]):
                        planes()
                    else:
                        pass
                except:
                    # legacy fix : if there is no param for axis in parameters
                    if (a == current["AxisValue"]):
                        planes()
                    else:
                        pass
            def planes():
                try:
                    if sign[current["PlaneSign"]](p, current["PlaneValue"]):
                        obj()
                    else:
                        pass
                except:
                    # legacy fix : if there is no param for planes in parameters
                    if (p == current["PlaneValue"]):
                        obj()
                    else:
                        pass
            def obj():
                if sign[current["ObjectSign"]](o, current["ObjectValue"]):
                    global globalContextPie
                    global globalIndexPie
                    global indexPie
                    globalIndexPie = current["Index"]

                    if globalIndexPie:
                        pieName = getParamIndex(globalIndexPie)
                        contextWorkbench = None
                        contextWorkbench = getParameterGroup(
                            pieName, "String", "ContextWorkbench")
                        activeWB = Gui.activeWorkbench().name()
                        activeWB = activeWB.split("Workbench")

                        if contextWorkbench == activeWB[0] or contextWorkbench == translate("ContextTab", "All Workbenches"):
                            globalContextPie = "True"
                            indexPie = current["Index"]
                else:
                    pass
            vertex()

        if globalContextPie == "True":
            return indexPie
        else:
            return None

    def listTopo():
        """ Handle conditions to trigger context mode """
        nonlocal contextPhase
        module = None
        try:
            g = Gui.ActiveDocument.getInEdit()
            module = g.Module
        except:
            pass

        if module is None or module == "SketcherGui":
            # nonlocal contextPhase
            sel = Gui.Selection.getSelectionEx()
            vertexes = 0
            edges = 0
            faces = 0
            objects = 0
            axis = 0
            planes = 0
            allList = []
            listAxis = [ 'X_Axis', 'Y_Axis', 'Z_Axis', 'H_Axis', 'V_Axis' ]
            listPlanes = [ 'XY_Plane', 'XZ_Plane', 'YZ_Plane' ]
            for i in sel:
                if i.ObjectName in listAxis or i.ObjectName in listPlanes:
                    allList.append(i.ObjectName)
                elif i.ObjectName.startswith("DatumPlane"):
                    planes = planes + 1
                elif i.ObjectName.startswith("DatumLine"):
                    axis = axis + 1
                elif i.ObjectName.startswith("DatumPoint"):
                    vertexes = vertexes + 1
                elif not i.SubElementNames:
                    objects = objects + 1
                else:
                    for a in i.SubElementNames:
                        allList.append(a)
            for i in allList:
                if i.startswith('Vertex') or i.startswith('ExternalVertex') or i.startswith('RootPoint'):
                    vertexes = vertexes + 1
                elif i.startswith('Edge') or i.startswith('ExternalEdge'):
                    edges = edges + 1
                elif i.startswith('Face'):
                    faces = faces + 1
                elif i.startswith('X_Axis') or i.startswith('Y_Axis') or i.startswith('Z_Axis') or i.startswith('H_Axis') or i.startswith('V_Axis') :
                    axis = axis + 1
                elif i.startswith('XY_Plane') or i.startswith('XZ_Plane') or i.startswith('YZ_Plane') :
                    planes = planes + 1
                else:
                    pass
            pieIndex = getContextPie(vertexes,
                                     edges,
                                     faces,
                                     objects,
                                     axis,
                                     planes)

            if pieIndex:
                pieName = getParamIndex(pieIndex)
                try:
                    config.get_params()["main"].SetString("ContextPie", pieName.encode("UTF-8"))
                except TypeError:
                    config.get_params()["main"].SetString("ContextPie", pieName)
                contextPhase = True

                PieMenuInstance.hide()

                activeWB = Gui.activeWorkbench().name()
                activeWB = activeWB.split("Workbench")
                contextWorkbench = None
                contextWorkbench = getParameterGroup(
                    pieName, "String", "ContextWorkbench")

                if contextWorkbench == activeWB[0] or contextWorkbench is None or contextWorkbench == translate("ContextTab", "All Workbenches"):
                    immediateTrigger = getParameterGroup(
                        pieName, "Bool", "ImmediateTriggerContext")
                    if immediateTrigger:
                        PieMenuInstance.showAtMouseInstance()
            else:
                contextPhase = False
        return contextPhase

    def addObserver():
        if config.get_params()["main"].GetBool("EnableContext"):
            Gui.Selection.addObserver(selObserver)
        else:
            Gui.Selection.removeObserver(selObserver)

    def getGuiActionMapAll():
        # WBs workaround 0.22.37436
        availableActions = {}
        duplicates = []

        wbContainer = mw.findChild(QtGui.QAction, "Std_Workbench")
        parentWbContainer = wbContainer.parent()
        wbGroup = parentWbContainer.findChild(QtGui.QActionGroup)
        for i in wbGroup.actions():
            if i.objectName() != "" and i.icon():
                availableActions[i.objectName()] = i
            else:
                pass

        for i in mw.findChildren(QtGui.QAction):
            if i.objectName() is not None:
                if i.objectName() != "" and i.icon():
                    if i.objectName() in availableActions:
                        pass
                    else:
                        availableActions[i.objectName()] = i
                else:
                    pass
            else:
                pass

        for d in duplicates:
            del availableActions[d]

        return availableActions

    def extractWorkbench(command):
        """ Get the workbench from command """
        cmd_parts = command.split("_")
        if cmd_parts[0] == "":
            workbench = "None"
        else:
            workbench = cmd_parts[0]
        return workbench

    def getActionData(action, actions, commands, workbenches):
        if not action.icon():
            return
        if actions is not None:
            if action in actions:
                pass
            else:
                actions.append(action)
        if commands is None and workbenches is None:
            return
        command = action.objectName()
        if len(command) == 0:
            workbench = "None"
        else:
            if commands is not None:
                if command in commands:
                    pass
                else:
                    commands.append(command)
            workbench = extractWorkbench(command)
        if workbenches is not None:
            if workbench not in workbenches:
                workbenches.append(workbench)

    def getGuiToolButtonData(idToolBar, actions, commands, workbenches):
        actionMapAll = getGuiActionMapAll()

        qt_version = QtCore.qVersion()
        qt_major_version = int(qt_version.split('.')[0])

        for i in actionMapAll:
            action = actionMapAll[i]

            if qt_major_version >= 6:
                # for Qt6
                associated_items = action.associatedObjects()
            else:
                # for Qt5
                associated_items = action.associatedWidgets()
            for widgets in associated_items:
                if widgets.windowTitle() == idToolBar:
                    getActionData(action, actions, commands, workbenches)

    def actualizeWorkbenchActions(actions, toolList, actionMap):
        for i in toolList:
            # rule out special case: there has to be an entry
            if i == "":
                pass
            elif i in actionMap:
                actions.append(actionMap[i])
            else:
                workbench = extractWorkbench(i)
                # rule out special case: unknown Std action
                if workbench == "Std":
                    pass
                else:
                    wbName = constants.workbench_map.get(
                        workbench, workbench + "Workbench")
                    try:
                        Gui.activateWorkbench(wbName)
                    except:
                        None
        return False

    def updateCommands(keyValue=None, context=False):
        # keyValue = None > Global shortcut
        # keyValue != None > Custom shortcut
        global triggerMode
        global loadedWorkbenches

        if not keyValue or keyValue is None:
            # context
            if context:
                text = getParam("ContextPie")

            # workbench
            elif not config.get_params()["main"].GetBool("ToolBar"):
                wb = Gui.activeWorkbench()
                wbName = wb.name()
                wbName = wbName.replace("Workbench", "")
                # workbench
                text = getPieName(wbName)

                # current Pie
                if text is None:
                    text = getParam("CurrentPie")
            # else:
                # text = keyValue
                context = False

            # toolbar
            elif config.get_params()["main"].GetBool("ToolBar"):
                toolbar = config.get_params()["main"].GetString("ToolBar")
                text = None
                context = False
                if ": " in toolbar:
                    toolbar_desc = toolbar.split(": ")
                    toolbar = toolbar_desc[1]
                    workbenches = toolbar_desc[0]
                    workbenches = workbenches.split(", ")
                    lastWorkbench = Gui.activeWorkbench()
                    for i in workbenches:
                        # rule out special cases
                        if i is None or i == "Std":
                            pass
                        else:
                            wbName = constants.workbench_map.get(i, i + "Workbench")
                        if (i + "Workbench") not in loadedWorkbenches:
                            try:
                                Gui.activateWorkbench(wbName)
                            except:
                                None
                            loadedWorkbenches.append(wbName)
                    Gui.activateWorkbench(lastWorkbench.__class__.__name__)
                else:
                    pass
                context = False
                actions = []
                getGuiToolButtonData(toolbar, actions, None, None)

        # for toolbar preview in preferences settings
        elif keyValue == "toolBarTab":
            context = False
            text = False
            items = []
            commands = []

            for index in range(listToolBar.count()):
                items.append(listToolBar.item(index))
                if items[index].isSelected():
                    sender = listToolBar.item(index)
                    getGuiToolButtonData(sender.text(), None, commands, None)

            actions = []
            actionMapAll = getGuiActionMapAll()
            while actualizeWorkbenchActions(actions, commands, actionMapAll):
                actionMapAll = getGuiActionMapAll()
            else:
                pass
            PieMenuInstance.add_commands(actions, False, "toolBarTab")

        else:
            # custom shortcut
            text = keyValue
            context = False

        if text:
            toolList = None
            indexList = getIndexList()
            for i in indexList:
                pie = getParamIndex(str(i))
                if pie == text:
                    group = config.get_params()["index"].GetGroup(str(i))
                    toolList = group.GetString("ToolList")
                else:
                    pass

            if toolList:
                toolList = toolList.split(".,.")
            else:
                toolList = []

            actions = []

            actionMapAll = getGuiActionMapAll()
            lastWorkbench = Gui.activeWorkbench()
            while actualizeWorkbenchActions(actions, toolList, actionMapAll):
                actionMapAll = getGuiActionMapAll()
            else:
                pass
            Gui.activateWorkbench(lastWorkbench.__class__.__name__)

            triggerMode = getParameterGroup(text, "String", "TriggerMode")
            state.app_state.hover_delay = getParameterGroup(text, "Int", "HoverDelay")

        else:
            pass

        if not keyValue == "toolBarTab":
            PieMenuInstance.add_commands(actions, context, text)

    def getGroup(mode=0):
        """
        Obtain the parameter group.
        When:
        mode = 0: read from comboBox at GUI
        mode = 1: read from CurrentPie parameter
        mode = 2: read from ContextPie parameter
        If it doesn't exists return default PieMenu group
        """

        if mode == 2:
            text = getParam("ContextPie")
        elif mode == 1:
            text = getParam("CurrentPie")
        else:
            text = cBox.currentText()
        group = None

        # Iterate over the available groups on indexList
        # to find the group stored on `text` var
        indexList = getIndexList()
        for i in indexList:
            pie = getParamIndex(str(i))
            if pie == text:
                group = config.get_params()["index"].GetGroup(str(i))
            else:
                pass
        if group:
            # group was found, good
            pass
        else:
            # return the default PieMenu group
            if 0 in indexList:
                group = config.get_params()["index"].GetGroup("0")
            else:
                setDefaultPie()
                try:
                    updateCommands()
                except:
                    None
                group = config.get_params()["index"].GetGroup("0")

        return group

    def setTheme():
        comboBoxTheme.blockSignals(True)
        theme = comboBoxTheme.currentText()
        config.get_params()["main"].SetString("Theme", theme)
        comboBoxTheme.blockSignals(False)
        try:
            if pieMenuDialog.isVisible():
                updatePiemenuPreview()
        except:
            None

    def getTheme():
        """ list all QSS files themes available """
        all_files = os.listdir(resources.stylepath)
        qss_files = [file for file in all_files if file.endswith(".qss")]
        available_styles = [file[:-4] for file in qss_files]
        comboBoxTheme.blockSignals(True)
        comboBoxTheme.clear()
        comboBoxTheme.addItems(available_styles)

        theme = config.get_params()["main"].GetString("Theme")
        index = comboBoxTheme.findText(theme)
        if index != -1:
            comboBoxTheme.setCurrentIndex(index)
        comboBoxTheme.blockSignals(False)

    def buttonList():
        indexList = getIndexList()

        for i in indexList:
            pie = getParamIndex(str(i))
            if pie == cBox.currentText():
                group = config.get_params()["index"].GetGroup(str(i))
                toolList = group.GetString("ToolList")
            else:
                pass

        if toolList:
            toolList = toolList.split(".,.")
        else:
            toolList = []

        actionMapAll = getGuiActionMapAll()
        lastWorkbench = Gui.activeWorkbench()

        for i in toolList:
            if i not in actionMapAll:
                # rule out special case: there has to be an entry
                if i == "":
                    pass
                else:
                    workbench = extractWorkbench(i)
                    if workbench not in loadedWorkbenches and "Workbench" not in workbench:
                        # rule out special case: unknown Std action
                        if workbench == "Std":
                            pass
                        else:
                            wbName = constants.workbench_map.get(
                                workbench, workbench + "Workbench")
                            try:
                                Gui.activateWorkbench(wbName)
                                loadedWorkbenches.append(workbench)
                            except:
                                None
                    else:
                        pass
            else:
                pass
        Gui.activateWorkbench(lastWorkbench.__class__.__name__)

        buttonListWidget.blockSignals(True)
        buttonListWidget.clearContents()
        buttonListWidget.setRowCount(0)

        shortcutCode = 48
        for i in toolList:
            if i in actionMapAll:

                rowPosition = buttonListWidget.rowCount()
                buttonListWidget.insertRow(rowPosition)

                actionItem = QtWidgets.QTableWidgetItem(
                    actionMapAll[i].text().replace("&", ""))
                actionItem.setData(QtCore.Qt.UserRole, i)
                actionItem.setIcon(actionMapAll[i].icon())
                actionItem.setToolTip(actionMapAll[i].toolTip())
                shortcutItem = QtWidgets.QTableWidgetItem()
                # prevent user to select shortcut in list
                shortcutItem.setFlags(QtCore.Qt.ItemIsEnabled)
                shortcutItem.setTextAlignment(QtCore.Qt.AlignCenter)

                if (actionMapAll[i].text()) == translate('PieMenuTab', 'Separator'):
                    shortcutItem.setText("")
                elif i.startswith(shortcutEntryPrefix):
                    # shortcut entries show their assigned key sequence while
                    # the tool-shortcut letter keeps advancing like in the pie
                    shortcutItem.setText(formatKeySequence(getShortcutEntryKey(i)))
                    shortcutItem.setToolTip(shortcutItem.text())
                    buttonListWidget.setItem(rowPosition, 0, shortcutItem)
                    # trick to jump form key 9 to key A in ascii list
                    if shortcutCode == 57:
                        shortcutCode = 64
                    shortcutCode += 1
                    # trick to avoid X key, which bug !
                    if shortcutCode == 88:
                        shortcutCode = 89
                else:
                    # we add shortcut till we are not beyond the letter Z
                    if shortcutCode <= 90:
                        shortcutItem.setText(chr(shortcutCode))
                        buttonListWidget.setItem(rowPosition, 0, shortcutItem)

                    # trick to jump form key 9 to key A in ascii list
                    if shortcutCode == 57:
                        shortcutCode = 64
                    shortcutCode += 1
                    # trick to avoid X key, which bug !
                    if shortcutCode == 88:
                        shortcutCode = 89

                buttonListWidget.setItem(rowPosition, 1, actionItem)

        buttonListWidget.blockSignals(False)

        showPiemenu.hide()
        PieMenuInstance.showPiemenuPreview(keyValue=cBox.currentText())
        showPiemenu.show()

    def cBoxUpdate(index=None):
        currentPie = getParam("CurrentPie")

        pieList = []
        indexList = getIndexList()
        for i in indexList:
            try:
                pieList.append(config.get_params()["index"].GetString(str(i)).decode("UTF-8"))
            except AttributeError:
                pieList.append(config.get_params()["index"].GetString(str(i)))
        duplicates = []
        for i in pieList:
            if i == currentPie:
                pass
            else:
                duplicates.append(i)
        duplicates.append(currentPie)

        pieList = sorted(duplicates)
        pieList.reverse()

        cBox.blockSignals(True)
        cBox.clear()

        for i in pieList:
            cBox.insertItem(0, i)
        cBox.blockSignals(False)

        if index is None:
            index = 0
        else:
            index = cBox.findText(index)

        cBox.setCurrentIndex(index)
        onPieChange()

    def getAssignedShortcut():
        shortcutsAssigned = [f"{act.whatsThis()} => {act.shortcut().toString()}"
                             for act in Gui.getMainWindow().findChildren(QtGui.QAction)
                             if not act.shortcut().isEmpty() and act.whatsThis()]
        shortcutList = getShortcutList()
        shortcutsAssigned.extend(shortcutList)
        # key sequences stored for shortcut entries hold no QAction shortcut,
        # read them from the parameter group so conflicts are still reported
        shortcutsGroup = App.ParamGet(
            "User parameter:BaseApp/PieMenu/Shortcuts")
        for num in getShortcutEntryNumbers():
            entryGroup = shortcutsGroup.GetGroup("Entry_" + num)
            key = entryGroup.GetString("Key")
            if key:
                name = entryGroup.GetString(
                    "Name") or translate("PieMenuTab", "Shortcut")
                shortcutsAssigned.append(f"{name} => {key}")
        return shortcutsAssigned

    def compareAndDisplayWarning(shortcutsAssigned, currentShortcut, label=None):
        if label is None:
            label = infoShortcut
        label.setText('')
        for assignedShortcut in shortcutsAssigned:
            command, shortcut = assignedShortcut.split(" => ")
            if shortcut.replace(" ", "").lower() == currentShortcut.lower():
                label.setText(
                    f' Warning: {currentShortcut} is already assigned for {command}')
                break

    def updateShortcutKey(newShortcut):
        if not newShortcut:
            state.app_state.shortcut_key = newShortcut
            setParameterGroup(cBox.currentText(), "String",
                              "ShortcutKey", state.app_state.shortcut_key)
            labelShortcut.setText(translate(
                "PieMenuTab", "Shortcut deleted! No shortcut assigned ") + state.app_state.shortcut_key)

        else:
            parties = set(newShortcut.replace(',', '+').split('+'))
            for partie in parties:
                if partie not in constants.touches_speciales and len(partie) > 1:
                    labelShortcut.setText(
                        translate("PieMenuTab", "Invalid shortcut! Current shortcut: ") + state.app_state.shortcut_key)
                else:
                    state.app_state.shortcut_key = newShortcut
                    setParameterGroup(cBox.currentText(),
                                      "String", "ShortcutKey", state.app_state.shortcut_key)
                    labelShortcut.setText(
                        translate("PieMenuTab", "New shortcut assigned: ") + state.app_state.shortcut_key)
        shortcutLineEdit.setText(state.app_state.shortcut_key)
        getShortcutList()

    def updateGlobalShortcutKey(newShortcut):
        if not newShortcut:
            state.app_state.global_shortcut_key = newShortcut
            config.get_params()["main"].SetString("GlobalShortcutKey", state.app_state.global_shortcut_key)
            labelGlobalShortcut.setText(translate("GlobalSettingsTab",
                                                  "Shortcut deleted ! No shortcut assigned ")
                                        + state.app_state.global_shortcut_key)

        else:
            parties = set(newShortcut.replace(',', '+').split('+'))
            invalidShortcut = any(
                partie not in constants.touches_speciales and len(partie) > 1
                for partie in parties)
            if invalidShortcut:
                labelGlobalShortcut.setText(translate("GlobalSettingsTab",
                                                      "Invalid shortcut ! Current global shortcut : ")
                                            + state.app_state.global_shortcut_key)
            else:
                state.app_state.global_shortcut_key = newShortcut
                config.get_params()["main"].SetString("GlobalShortcutKey", state.app_state.global_shortcut_key)
                labelGlobalShortcut.setText(translate("GlobalSettingsTab",
                                                      "New global shortcut assigned: ")
                                            + state.app_state.global_shortcut_key)
        actionKey.setShortcut(QtGui.QKeySequence(state.app_state.global_shortcut_key))
        globalShortcutLineEdit.setText(state.app_state.global_shortcut_key)

    def infoPopup():
        msg = """
            <h2>Pie menu</h2>
            <p style='font-weight:normal;font-style:italic;'>version """ + PIE_MENU_VERSION + """</p>
            <p style='font-weight:normal;'>This macro adds pie menu to FreeCAD GUI</p>
            <hr>
            <h2>Licence</h2>
            <p style='font-weight:normal;'>Copyright (C) 2024 Grubuntu, Pgilfernandez, Hasecilu @ FreeCAD</p>
            <p style='font-weight:normal;'>Copyright (C) 2022, 2023 mdkus @ FreeCAD</p>
            <p style='font-weight:normal;'>Copyright (C) 2016, 2017 triplus @ FreeCAD</p>
            <p style='font-weight:normal;'>Copyright (C) 2015,2016 looo @ FreeCAD</p>
            <p style='font-weight:normal;'>Copyright (C) 2015 microelly <microelly2@freecadbuch.de></p>
            <p style='font-weight:normal;'>This library is free software; you can redistribute it and/or modify it under the terms of the GNU Lesser General Public License as published by the Free Software Foundation; either version 2.1 of the License, or (at your option) any later version.</p>
            <p style='font-weight:normal;'>This library is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more details.</p>
            <p style='font-weight:normal;'>You should have received a copy of the GNU Lesser General Public License along with this library; if not, write to the Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA</p>
        """
        QtGui.QMessageBox.question(None, "Help", msg, QtGui.QMessageBox.Ok)

    def documentationLink():
        """Open PieMenu documentation using the Help settings."""
        from Help import show
        pieMenuDialog.close()
        # Open a wiki page
        show("PieMenu Workbench")

    def getAllActions():
        """ Return the list of all Freecad's action with an icon """
        all_actions = Gui.getMainWindow().findChildren(QtGui.QAction)
        action_list = []

        for action in all_actions:
            icon = action.icon()
            if not icon.isNull() and action.data() is not None and action not in action_list:
                action_list.append(action)
        return action_list

    def getIconPieMenu(iconPath=""):
        """ Return icon object corresponding to iconPath  through all actions """
        iconAction = iconPath
        action_list = getAllActions()

        if iconPath == "":
            iconAction = resources.iconPieMenuLogo
        else:
            for action in action_list:
                if action.data() == iconPath:
                    iconAction = action.icon()
        return iconAction

    def onPieChange():
        """ Update values for all settings """
        state.app_state.sub_group_selected = None
        onResetContextTable()
        buttonList()
        toolList()
        setContextConditions()
        getShortcutList()

        iconPath = getParameterGroup(cBox.currentText(), "String", "IconPath")
        defaultPie = getParameterGlobal("String", "CurrentPie")
        index = cBox.findText(defaultPie)
        shape = getShape(cBox.currentText())
        radiusSize = getParameterGroup(cBox.currentText(), "Int", "Radius")
        buttonSize = getParameterGroup(cBox.currentText(), "Int", "Button")
        numColumn = getParameterGroup(cBox.currentText(), "Int", "NumColumn")
        iconSpacing = getParameterGroup(
            cBox.currentText(), "Int", "IconSpacing")
        commandPerCircle = getParameterGroup(
            cBox.currentText(), "Int", "CommandPerCircle")
        displayCommandName = getParameterGroup(
            cBox.currentText(), "Bool", "DisplayCommand")
        displayPreselect = getParameterGroup(
            cBox.currentText(), "Bool", "DisplayPreselect")
        triggerMode = getParameterGroup(
            cBox.currentText(), "String", "TriggerMode")
        triggerContext = getParameterGroup(
            cBox.currentText(), "Bool", "ImmediateTriggerContext")
        hoverDelay = getParameterGroup(cBox.currentText(), "Int", "HoverDelay")
        enableShortcut = getParameterGroup(
            cBox.currentText(), "Bool", "EnableShorcut")
        displayShortcut = getParameterGroup(
            cBox.currentText(), "Bool", "DisplayShorcut")
        shortcutLabelSize = getParameterGroup(
            cBox.currentText(), "Int", "ShortcutLabelSize")
        shortcutKey = getParameterGroup(
            cBox.currentText(), "String", "ShortcutKey")
        globalKeyToggle = getParameterGlobal("Bool", "GlobalKeyToggle")
        displaySpinBox = getParameterGlobal("Bool", "DisplaySpinBox")

        icon = getIconPieMenu(iconPath)
        buttonIconPieMenu.setIcon(QtGui.QIcon(icon))

        checkboxDefaultPie.blockSignals(True)
        if defaultPie == cBox.currentText():
            checkboxDefaultPie.setChecked(True)
        else:
            checkboxDefaultPie.setChecked(False)
        checkboxDefaultPie.blockSignals(False)

        cBox.setItemIcon(index, iconDefault)

        onContextWorkbench()
        setWbForPieMenu()
        spacingGroup = getGroup()
        for packed, equally, parameter in (
                (radioInnerPacked, radioInnerEquallySpaced, "PackInnerIcons"),
                (radioOuterPacked, radioOuterEquallySpaced, "PackOuterIcons")):
            packed.blockSignals(True)
            equally.blockSignals(True)
            isPacked = spacingGroup.GetBool(parameter, False)
            packed.setChecked(isPacked)
            equally.setChecked(not isPacked)
            packed.blockSignals(False)
            equally.blockSignals(False)
        onShape(shape)
        spinRadius.setValue(radiusSize)
        spinButton.setValue(buttonSize)
        spinNumColumn.setValue(numColumn)
        spinIconSpacing.setValue(iconSpacing)
        spinCommandPerCircle.setValue(commandPerCircle)
        checkboxDisplayCommandName.blockSignals(True)
        checkboxDisplayCommandName.setChecked(displayCommandName)
        checkboxDisplayCommandName.blockSignals(False)
        checkboxDisplayPreselect.blockSignals(True)
        checkboxDisplayPreselect.setChecked(displayPreselect)
        checkboxDisplayPreselect.blockSignals(False)
        checkboxDisplaySpinBox.blockSignals(True)
        checkboxDisplaySpinBox.setChecked(displaySpinBox)
        checkboxDisplaySpinBox.blockSignals(False)
        setTriggerMode(triggerMode)
        radioButtonPress.setChecked(triggerMode == "Press")
        radioButtonHover.setChecked(triggerMode == "Hover")
        spinHoverDelay.setValue(hoverDelay)
        toolShortcutGroup.setChecked(enableShortcut)
        buttonListWidget.setColumnHidden(0, not enableShortcut)
        checkboxDisplayShortcut.setChecked(displayShortcut)
        spinShortcutLabelSize.setValue(shortcutLabelSize)
        shortcutLineEdit.setText(shortcutKey)
        labelShortcut.setText(
            translate("PieMenuTab", "Current shortcut: ") + shortcutKey)
        checkboxTriggerContext.setChecked(triggerContext)
        checkboxGlobalKeyToggle.setChecked(globalKeyToggle)
        infoShortcut.setText('')
        updateContextConditions()

    def inputTextDialog(title):
        """ Dialog box for PieMenu name """
        info1 = translate("PieMenuTab", "Please insert menu name")
        info2 = translate("PieMenuTab", "Menu already exists")
        d = QtGui.QInputDialog(pieMenuDialog)
        d.setModal(True)
        d.setInputMode(QtGui.QInputDialog.InputMode.TextInput)
        text, ok = QtGui.QInputDialog.getText(pieMenuDialog, title, info1)
        if not ok:
            return text, ok
        while not text:
            text, ok = QtGui.QInputDialog.getText(pieMenuDialog, title, info1)
            if not ok:
                return text, ok
            else:
                pass
        index = cBox.findText(text)
        info = info2
        while index != -1:
            d = QtGui.QInputDialog(pieMenuDialog)
            d.setModal(True)
            d.setInputMode(QtGui.QInputDialog.InputMode.TextInput)
            text, ok = QtGui.QInputDialog.getText(pieMenuDialog, title, info)
            if ok:
                if text:
                    index = cBox.findText(text)
                    info = info2
                else:
                    info = info1
            else:
                return text, ok
        return text, ok

    def createPie(text):
        """ Create new PieMenu """
        pieList = []
        indexList = getIndexList()
        for i in indexList:
            pieList.append(config.get_params()["index"].GetString(str(i)))
        if text in pieList:
            pass
        elif not text:
            pass
        else:
            # Read the previous menu settings before the new index is
            # registered, so a recycled index is not mistaken for it.
            sourceSettings = getLastCreatedTabSettings()
            if text == "restore_default_pie" and text.lower():
                setDefaultPie(restore=True)
            else:
                x = 1
                while x in indexList and x < 999:
                    x = x + 1
                else:
                    indexNumber = x
                indexList.append(indexNumber)
                temp = []
                for i in indexList:
                    temp.append(str(i))
                indexList = temp
                config.get_params()["index"].SetString("IndexList", ".,.".join(indexList))
                indexNumber = str(indexNumber)
                try:
                    config.get_params()["index"].SetString(indexNumber, text.encode('UTF-8'))
                except TypeError:
                    config.get_params()["index"].SetString(indexNumber, text)

            cBoxUpdate(text)
            # set defaults values
            group = getGroup()
            setDefaultValues(group, sourceSettings)
            # remember this menu so the next created menu inherits its
            # Pie menu tab settings.
            if text != "restore_default_pie":
                config.get_params()["main"].SetString(
                    "LastCreatedPie", indexNumber)
            # default keyboard shortcut for a newly created pie menu, but only
            # when it is not already used by another pie (duplicates make Qt
            # cycle between them).
            if newPieShortcut:
                shortcutInUse = any(
                    config.get_params()["index"].GetGroup(str(i)).GetString("ShortcutKey")
                    and QKeySequence(config.get_params()["index"].GetGroup(
                        str(i)).GetString("ShortcutKey")).toString()
                    == QKeySequence(newPieShortcut).toString()
                    for i in getIndexList())
                if not shortcutInUse:
                    group.SetString("ShortcutKey", newPieShortcut)
            # createNestedPieMenus()
            reloadWorkbench()
            onPieChange()

        return config.get_params()["index"].GetGroup(indexNumber)

    # Settings shown on the Pie menu tab that a new menu inherits from the
    # previously created menu. Each entry is (name, type, hard-coded fallback);
    # a fallback of None keeps the key unset, preserving the legacy behaviour.
    defaultPieTabKeys = (
        ("Radius", "Int", 80),
        ("Button", "Int", 32),
        ("Shape", "String", "Pie"),
        ("TriggerMode", "String", "Press"),
        ("HoverDelay", "Int", 100),
        ("NumColumn", "Int", 4),
        ("IconSpacing", "Int", None),
        ("CommandPerCircle", "Int", 5),
        ("PackOuterIcons", "Bool", False),
        ("PackInnerIcons", "Bool", False),
        ("EnableShorcut", "Bool", False),
        ("DisplayCommand", "Bool", None),
        ("DisplayPreselect", "Bool", False),
        ("DisplayShorcut", "Bool", None),
        ("ShortcutLabelSize", "Int", 8),
    )

    def getLastCreatedTabSettings():
        r""" Read the Pie menu tab settings of the previously created menu.

        \return A dict mapping setting name to stored value, or an empty dict
        when no previously created menu is available.
        """
        settings = {}
        sourceIndex = config.get_params()["main"].GetString("LastCreatedPie")
        if not sourceIndex:
            return settings
        try:
            sourceNumber = int(sourceIndex)
        except ValueError:
            return settings
        if sourceNumber not in getIndexList():
            return settings
        source = config.get_params()["index"].GetGroup(sourceIndex)
        present = set(name for _type, name, _value in source.GetContents())
        for name, paramType, _fallback in defaultPieTabKeys:
            if name not in present:
                continue
            if paramType == "Int":
                settings[name] = source.GetInt(name)
            elif paramType == "String":
                settings[name] = source.GetString(name)
            elif paramType == "Bool":
                settings[name] = source.GetBool(name)
        return settings

    def setDefaultValues(group, sourceSettings=None):
        r""" Add defaults values in user.cfg.

        \param group Parameter group of the newly created Pie menu.
        \param sourceSettings Pie menu tab settings of the previously created
        menu; missing keys fall back to the hard-coded defaults.
        """
        if sourceSettings is None:
            sourceSettings = {}
        for name, paramType, fallback in defaultPieTabKeys:
            if name in sourceSettings:
                value = sourceSettings[name]
            elif fallback is not None:
                value = fallback
            else:
                continue
            if paramType == "Int":
                group.SetInt(name, value)
            elif paramType == "String":
                group.SetString(name, value)
            elif paramType == "Bool":
                group.SetBool(name, value)

    def onButtonAddPieMenu():
        """ Dialog to add PieMenu """
        text, ok = inputTextDialog(translate("PieMenuTab", "New menu"))
        if not ok:
            return
        createPie(text)

    def onButtonRemovePieMenu():
        """ Remove PieMenu """
        currentPie = getParam("CurrentPie")
        contextPie = getParam("ContextPie")

        indexList = getIndexList()
        for i in indexList:
            pie = getParamIndex(str(i))
            if pie == cBox.currentText():
                config.get_params()["index"].RemGroup(str(i))
                config.get_params()["index"].RemString(str(i))

                indexList.remove(i)
                temp = []
                for n in indexList:
                    temp.append(str(n))
                indexList = temp
                config.get_params()["index"].SetString("IndexList", ".,.".join(indexList))

                globaltoolbar = App.ParamGet(
                    'User parameter:BaseApp/Workbench/Global/Toolbar/Custom_PieMenu')
                globaltoolbar.RemString('PieMenu_' + pie)

                # special case treatment
                if pie == currentPie:
                    currentPie = "View"
                    try:
                        config.get_params()["main"].SetString(
                            "CurrentPie", currentPie.encode('UTF-8'))
                    except TypeError:
                        config.get_params()["main"].SetString("CurrentPie", currentPie)
                if pie == contextPie:
                    config.get_params()["main"].RemString("ContextPie")

                # remove nested_menu in toollist
                for i in indexList:
                    toolListe = None
                    group = config.get_params()["index"].GetGroup(str(i))
                    toolListe = group.GetString("ToolList")

                    if toolListe:
                        toolListe = toolListe.split(".,.")
                    else:
                        toolListe = []

                    stringToFind = 'PieMenu_' + pie

                    if (stringToFind) in toolListe:
                        toolListe.remove(stringToFind)
                        toolListe = group.SetString(
                            "ToolList", ".,.".join(toolListe))
                break
            else:
                pass

        cBoxUpdate()

        if cBox.currentIndex() == -1:
            setDefaultPie()
            cBoxUpdate()
        else:
            pass

    def onButtonRenamePieMenu():
        """ Rename PieMenu """
        text, ok = inputTextDialog(translate("PieMenuTab", "Rename menu"))
        if not ok:
            return
        indexList = getIndexList()
        currentPie = getParam("CurrentPie")
        for i in indexList:
            pie = getParamIndex(str(i))
            if pie == cBox.currentText():
                try:
                    config.get_params()["index"].SetString(str(i), text.encode('UTF-8'))
                except TypeError:
                    config.get_params()["index"].SetString(str(i), text)
                if pie == currentPie:
                    try:
                        config.get_params()["main"].SetString("CurrentPie", text.encode('UTF-8'))
                    except TypeError:
                        config.get_params()["main"].SetString("CurrentPie", text)
                else:
                    pass

                # rename nested_menu in toollist
                for i in indexList:
                    toolListe = None

                    group = config.get_params()["index"].GetGroup(str(i))
                    toolListe = group.GetString("ToolList")

                    if toolListe:
                        toolListe = toolListe.split(".,.")
                    else:
                        toolListe = []

                    stringToFind = 'PieMenu_' + pie

                    if (stringToFind) in toolListe:
                        index = toolListe.index(stringToFind)
                        toolListe[index] = 'PieMenu_' + text
                        toolListe = group.SetString(
                            "ToolList", ".,.".join(toolListe))

        globaltoolbar = App.ParamGet(
            'User parameter:BaseApp/Workbench/Global/Toolbar/Custom_PieMenu')
        globaltoolbar.RemString('PieMenu_' + pie)
        Gui.addCommand('PieMenu_' + text, NestedPieMenu(text))
        globaltoolbar.SetString('PieMenu_' + text, 'FreeCAD')

        reloadWorkbench()
        toolList()
        cBoxUpdate(text)

    def getCurrentMenuIndex(currentMenuName):
        """ Get the index through list of PieMenus in parameter """
        indexList = getIndexList()
        for i in indexList:
            indexName = config.get_params()["index"].GetString(str(i))
            if indexName == currentMenuName:
                return str(i)
        return "-1"

    def onButtonCopyPieMenu():
        """ Dialog for copy PieMenu """
        text, ok = inputTextDialog(translate("PieMenuTab", "Copy menu"))
        if not ok:
            return

        indexOrg = getCurrentMenuIndex(cBox.currentText())

        pieList = []
        indexList = getIndexList()
        for i in indexList:
            pieList.append(config.get_params()["index"].GetString(str(i)))

        if text in pieList:
            pass
        elif not text:
            pass
        else:
            x = 1

            while x in indexList and x < 999:
                x = x + 1
            else:
                indexCopy = x

            indexList.append(indexCopy)

            temp = []

            for i in indexList:
                temp.append(str(i))

            indexList = temp

            config.get_params()["index"].SetString("IndexList", ".,.".join(indexList))

            indexCopy = str(indexCopy)
            grpOrg = config.get_params()["index"].GetGroup(indexOrg)
            grpCopy = config.get_params()["index"].GetGroup(indexCopy)
            grpOrg.CopyTo(grpCopy)
            grpCopy.SetString("ShortcutKey", "")  # clear shortcutkey

            grpCntOrg = grpOrg.GetGroup("Context")
            grpCntCopy = grpCopy.GetGroup("Context")
            grpCntOrg.CopyTo(grpCntCopy)

            try:
                config.get_params()["index"].SetString(indexCopy, text.encode('UTF-8'))
            except TypeError:
                config.get_params()["index"].SetString(indexCopy, text)

        cBoxUpdate(text)

    def onDefaultPie(state):
        """ Set the selected PieMenu as default PieMenu """
        if state == 2:
            config.get_params()["main"].SetString("CurrentPie", cBox.currentText())
        currentPie = config.get_params()["main"].GetString("CurrentPie")
        index = cBox.findText(currentPie)
        cBox.setItemIcon(index, iconDefault)
        cBoxUpdate(cBox.currentText())

    def getListWorkbenches():
        """ Return a sorted list of workbenches for combobox """
        workenchList = Gui.listWorkbenches()
        wbList = []
        for i in workenchList:
            wbName = i.replace("Workbench", "")
            wbList.append(wbName)
        wbList.sort()
        if 'None' in wbList:
            wbList.remove('None')
            wbList.insert(0, 'None')

        return wbList

    def getWbAlreadySet():
        """ Check if a workbench is already set for a PieMenu """
        indexList = getIndexList()
        wbAlreadySet = []
        for i in indexList:
            group = config.get_params()["index"].GetGroup(str(i))
            defWb = group.GetString("DefaultWorkbench")
            if defWb != 'None':
                wbAlreadySet.append(defWb)

        return wbAlreadySet

    def setWbForPieMenu():
        """ Set workbench to a dedicate PieMenu """
        comboWbForPieMenu.blockSignals(True)
        wbList = getListWorkbenches()
        wbAlreadySet = getWbAlreadySet()

        for item in wbList[:]:
            if item in wbAlreadySet:
                wbList.remove(item)
                wbAlreadySet.remove(item)

        group = getGroup(mode=0)
        defWorkbench = group.GetString("DefaultWorkbench")
        wbList.append(defWorkbench)
        if 'None' not in wbList:
            wbList.insert(0, 'None')

        comboWbForPieMenu.clear()
        comboWbForPieMenu.addItems(wbList)
        index = comboWbForPieMenu.findText(defWorkbench)
        if index != -1:
            comboWbForPieMenu.setCurrentIndex(index)
        comboWbForPieMenu.blockSignals(False)

    def onContextWorkbench():
        """ Handle when a workbench is set to a PieMenu in context tab """
        comboContextWorkbench.blockSignals(True)
        wbList = getListWorkbenches()

        contextWorkbench = getParameterGroup(
            cBox.currentText(), "String", "ContextWorkbench")
        wbList.append(contextWorkbench)
        if "None" in wbList:
            wbList.remove("None")

        if translate('ContextTab', 'None (Disable)') not in wbList:
            wbList.insert(0, translate('ContextTab', 'None (Disable)'))

        if translate('ContextTab', 'All Workbenches') not in wbList:
            wbList.insert(0,  translate('ContextTab', 'All Workbenches'))

        notDuplicate = []
        for i in wbList:
            if i not in notDuplicate:
                notDuplicate.append(i)

        comboContextWorkbench.clear()
        comboContextWorkbench.addItems(notDuplicate)
        index = comboContextWorkbench.findText(contextWorkbench)
        if index != -1:
            comboContextWorkbench.setCurrentIndex(index)
        comboContextWorkbench.blockSignals(False)

    def onWbForPieMenu():
        """ Set Default Workbench in parameters """
        group = getGroup()
        defWorkbench = comboWbForPieMenu.currentText()
        group.SetString("DefaultWorkbench", defWorkbench)

    def setContextWorkbench():
        """ Set Context Workbench in parameters """
        group = getGroup()
        contextWorkbench = comboContextWorkbench.currentText()
        group.SetString("ContextWorkbench", contextWorkbench)

    def getPieName(wbName):
        """ Return PieMenu name corresponding to the setting Default Workbench """
        text = None
        indexList = getIndexList()
        for i in indexList:
            pie = getParamIndex(str(i))
            group = config.get_params()["index"].GetGroup(str(i))
            defWb = group.GetString("DefaultWorkbench")
            if defWb == wbName:
                text = pie
        return text

    def updatePiemenuPreview(key=None):
        """ Update the preview of PieMenu in preview Tab """
        try:
            showPiemenu.hide()
            if key == "toolBarTab":
                PieMenuInstance.showPiemenuPreview("toolBarTab")
            else:
                PieMenuInstance.showPiemenuPreview(keyValue=cBox.currentText())
            showPiemenu.show()
        except:
            None

    def onSpinShortcutLabelSize():
        """ Set shortcut label size """
        group = getGroup()
        value = spinShortcutLabelSize.value()
        group.SetInt("ShortcutLabelSize", value)
        try:
            if pieMenuDialog.isVisible():
                updatePiemenuPreview()
        except:
            None

    def setShape():
        """ Set shape of the PieMenu """
        group = getGroup(mode=0)
        comboShape.blockSignals(True)
        shape = comboShape.currentText()
        group.SetString("Shape", shape)
        comboShape.blockSignals(False)
        onShape(shape)
        try:
            if pieMenuDialog.isVisible():
                updatePiemenuPreview()
        except:
            None

    def onShape(shape):
        """ Handle the visibilty of buttons/boxes depending of the shape """
        iconSpacingGroup.setVisible(shape == "Pie")
        try:
            if pieMenuDialog.isVisible():

                if shape in ["TableTop", "TableDown", "TableLeft", "TableRight"]:
                    spinNumColumn.setEnabled(True)
                    labelNumColumn.setVisible(True)
                    spinNumColumn.setVisible(True)
                else:
                    spinNumColumn.setEnabled(False)
                    labelNumColumn.setVisible(False)
                    spinNumColumn.setVisible(False)

                if shape in ["UpDown", "LeftRight", "TableTop", "TableDown", "TableLeft", "TableRight", "Concentric", "Star"]:
                    labelIconSpacing.setVisible(True)
                    spinIconSpacing.setEnabled(True)
                    spinIconSpacing.setVisible(True)
                else:
                    labelIconSpacing.setVisible(False)
                    spinIconSpacing.setEnabled(False)
                    spinIconSpacing.setVisible(False)

                if shape in ["TableTop", "TableDown"]:
                    labelNumColumn.setText(
                        translate("PieMenuTab", "Number of columns:"))
                else:
                    labelNumColumn.setText(
                        translate("PieMenuTab", "Number of rows:"))

                group = getGroup()
                selected = set(group.GetString("ToolList").split(".,."))
                assignedOuter = set(group.GetString("OuterToolList").split(".,."))
                outerRing = shape == "Pie" and (
                    bool((selected & assignedOuter) - {""})
                    or group.GetBool("PackInnerIcons", False))
                if shape in ["Pie", "LeftRight"]:
                    labeldisplayCommandName.setVisible(True)
                    checkboxDisplayCommandName.setVisible(True)
                    checkboxDisplayCommandName.setEnabled(not outerRing)

                else:
                    labeldisplayCommandName.setVisible(False)
                    checkboxDisplayCommandName.setVisible(False)
                    checkboxDisplayCommandName.setEnabled(False)

                if shape in ["Concentric", "Star"]:
                    labelCommandPerCircle.setVisible(True)
                    spinCommandPerCircle.setEnabled(True)
                    spinCommandPerCircle.setVisible(True)
                else:
                    labelCommandPerCircle.setVisible(False)
                    spinCommandPerCircle.setEnabled(False)
                    spinCommandPerCircle.setVisible(False)

                if shape in ["Pie", "RainbowUp", "RainbowDown"]:
                    labelDisplayPreselect.setVisible(True)
                    checkboxDisplayPreselect.setVisible(True)
                    checkboxDisplayPreselect.setEnabled(not outerRing)
                else:
                    labelDisplayPreselect.setVisible(False)
                    checkboxDisplayPreselect.setVisible(False)
                    checkboxDisplayPreselect.setEnabled(False)

            # Available for all shapes
            labelShortcutSize.setVisible(True)
            spinShortcutLabelSize.setVisible(True)
            spinShortcutLabelSize.setEnabled(True)

        except:
            None

    def getShape(keyValue=None):
        """ Get value of shape of current PieMenu """
        if keyValue is None:
            keyValue = getParam("CurrentPie")
        group = getGroup()
        shape = group.GetString("Shape")

        indexList = getIndexList()
        for i in indexList:
            try:
                pieName = config.get_params()["index"].GetString(str(i)).decode("UTF-8")
            except AttributeError:
                pieName = config.get_params()["index"].GetString(str(i))
            if pieName == keyValue:
                param = config.get_params()["index"].GetGroup(str(i))
                shape = param.GetString("Shape")

        comboShape.blockSignals(True)
        comboShape.clear()
        # TODO only place available_shape is used: inline
        comboShape.addItems(constants.available_shape)
        index = comboShape.findText(shape)
        if index != -1:
            comboShape.setCurrentIndex(index)
        comboShape.blockSignals(False)

        return shape

    def onRingIconSpacing(parameter, checked):
        """Save each ring's spacing mode and refresh the preview."""
        getGroup().SetBool(parameter, checked)
        onShape(comboShape.currentText())
        updatePiemenuPreview()

    def onDisplayCommandName(state):
        """ Set parameter to show or not 'Command names' """
        indexList = getIndexList()
        for i in indexList:
            pieName = getParamIndex(str(i))
            if pieName == cBox.currentText():
                param = config.get_params()["index"].GetGroup(str(i))
                param.SetBool("DisplayCommand", state)
        try:
            if pieMenuDialog.isVisible():
                updatePiemenuPreview()
        except:
            None

    def onDisplaySpinBox(state):
        """ Set parameter to show or not fast SpinBox """
        if state == 2 or state == 1:
            config.get_params()["main"].SetBool("DisplaySpinBox", True)
        else:
            config.get_params()["main"].SetBool("DisplaySpinBox", False)
        updatePiemenuPreview()

    def onDisplayPreselect(state):
        """ Set parameter to show or not 'Preselect button' """
        indexList = getIndexList()
        for i in indexList:
            pieName = getParamIndex(str(i))
            if pieName == cBox.currentText():
                param = config.get_params()["index"].GetGroup(str(i))
                param.SetBool("DisplayPreselect", state)
        try:
            if pieMenuDialog.isVisible():
                updatePiemenuPreview()
        except:
            None

    def onEnableShortcut(state):
        """ Set parameter for enable or not 'Shortcut Tool' """
        if state:
            spinShortcutLabelSize.setEnabled(True)
            buttonListWidget.setColumnHidden(0, False)
            checkboxDisplayShortcut.setEnabled(True)

        else:
            spinShortcutLabelSize.setEnabled(False)
            buttonListWidget.setColumnHidden(0, True)
            checkboxDisplayShortcut.setEnabled(False)

        indexList = getIndexList()
        for i in indexList:
            pieName = getParamIndex(str(i))
            if pieName == cBox.currentText():
                param = config.get_params()["index"].GetGroup(str(i))
                param.SetBool("EnableShorcut", state)
        try:
            if pieMenuDialog.isVisible():
                updatePiemenuPreview()
        except:
            None

    def onDisplayShortcut(state):
        """ Set parameter for display or not 'Shortcut Tool' """
        if state == 2:
            spinShortcutLabelSize.setEnabled(True)
        else:
            spinShortcutLabelSize.setEnabled(False)

        indexList = getIndexList()
        for i in indexList:
            pieName = getParamIndex(str(i))
            if pieName == cBox.currentText():
                param = config.get_params()["index"].GetGroup(str(i))
                param.SetBool("DisplayShorcut", state)
        updatePiemenuPreview()

    def onTriggerContext(state):
        """ Set parameter for immediate trigger context mode """
        indexList = getIndexList()
        for i in indexList:
            pieName = getParamIndex(str(i))
            if pieName == cBox.currentText():
                param = config.get_params()["index"].GetGroup(str(i))
                param.SetBool("ImmediateTriggerContext", state)

    def onNumColumn():
        """ Set NUmber of column """
        group = getGroup()
        value = spinNumColumn.value()
        group.SetInt("NumColumn", value)
        updatePiemenuPreview()

    def onIconSpacing():
        """ Set Icon spacing """
        group = getGroup()
        value = spinIconSpacing.value()
        group.SetInt("IconSpacing", value)
        updatePiemenuPreview()

    def onCommandPerCircle():
        """ Set number of command per circle """
        group = getGroup()
        value = spinCommandPerCircle.value()
        group.SetInt("CommandPerCircle", value)
        updatePiemenuPreview()

    def onSpinHoverDelay():
        """ Set TriggerMode in parameter """
        value = spinHoverDelay.value()
        indexList = getIndexList()
        for i in indexList:
            pieName = getParamIndex(str(i))
            if pieName == cBox.currentText():
                param = config.get_params()["index"].GetGroup(str(i))
                param.SetInt("HoverDelay", value)

    def onSpinRadius():
        """ Set radius """
        group = getGroup()
        value = spinRadius.value()
        group.SetInt("Radius", value)
        updatePiemenuPreview()

    def onSpinButton():
        """ Set button size """
        group = getGroup()
        value = spinButton.value()
        group.SetInt("Button", value)
        updatePiemenuPreview()

    def onSpinDelayRightClick():
        """ Set delay for right click to trigger """
        value = spinDelayRightClick.value()
        config.get_params()["main"].SetInt("DelayRightClick", value)

    def onShowQuickMenu(state):
        """ Set visibility of Quickmenu """
        if state == 2:
            config.get_params()["main"].SetBool("ShowQuickMenu", True)
            contextList()
            addObserver()
        else:
            config.get_params()["main"].SetBool("ShowQuickMenu", False)
        updatePiemenuPreview()

    def onRightClickTrigger(state):
        """ Set right click trigger """
        if state == 2:
            config.get_params()["main"].SetBool("RightClickTrigger", True)
            spinDelayRightClick.setEnabled(True)
        else:
            config.get_params()["main"].SetBool("RightClickTrigger", False)
            spinDelayRightClick.setEnabled(False)

    def onContext(state):
        """ Set context mode activation """
        if state == 2 or state == 1:
            config.get_params()["main"].SetBool("EnableContext", True)
            contextList()
        else:
            config.get_params()["main"].SetBool("EnableContext", False)
        addObserver()

    def toolList():
        """Refresh the command list, retaining the current search filter."""
        searchInToolList(searchLineEdit.text())

    def onAddToolBar():
        """ create a menu from an existing toolbar  """
        items = []
        commands = []
        for index in range(listToolBar.count()):
            items.append(listToolBar.item(index))
        text, ok = inputTextDialog(translate("PieMenuTab", "New menu"))
        if not ok:
            return text, ok
        else:
            newPieGroup = createPie(text)
            toolbar = listToolBar.currentItem()
            getGuiToolButtonData(toolbar.text(), None, commands, None)
            newPieGroup.SetString("ToolList", ".,.".join(commands))
            newPieGroup.SetString("Shape", "Pie")
            tabs.setCurrentIndex(0)
        onBackToSettings()
        updatePiemenuPreview()

    def showListToolBar():
        """ show list of tools of an existing toolbar  """
        items = []
        commands = []

        for index in range(listToolBar.count()):
            items.append(listToolBar.item(index))
            if items[index].isSelected():
                sender = listToolBar.item(index)
                getGuiToolButtonData(sender.text(), None, commands, None)

        buttonListWidget.blockSignals(True)
        buttonListWidget.clearContents()
        buttonListWidget.setRowCount(0)

        actionMapAll = getGuiActionMapAll()
        for i in commands:
            if i in actionMapAll:
                rowPosition = buttonListWidget.rowCount()
                buttonListWidget.insertRow(rowPosition)
                actionItem = QtWidgets.QTableWidgetItem(
                    actionMapAll[i].text().replace("&", ""))
                actionItem.setData(QtCore.Qt.UserRole, i)
                actionItem.setIcon(actionMapAll[i].icon())
                actionItem.setFlags(QtCore.Qt.ItemIsEnabled)
                buttonListWidget.setItem(rowPosition, 1, actionItem)
                actionItem.setToolTip(actionMapAll[i].toolTip())

        buttonListWidget.blockSignals(False)
        updatePiemenuPreview("toolBarTab")

    def sortToolListByColumn(index):
        """ Tri alterné des colonnes avec indicateur """

        if index in (0, 1):
            toolListWidget.horizontalHeader().setSortIndicatorShown(False)
            return
        else:
            global sortOrder
            toolListWidget.horizontalHeader().setSortIndicatorShown(True)
            toolListWidget.sortItems(index, sortOrder)
            toolListWidget.horizontalHeader().setSortIndicator(index, sortOrder)
            # Alterner le tri pour le prochain clic
            sortOrder = QtCore.Qt.DescendingOrder if sortOrder == QtCore.Qt.AscendingOrder else QtCore.Qt.AscendingOrder

    def onToolListWidget(item):
        """Assign a command to one ring, or remove it when neither is checked."""
        if item.column() not in (0, 1):
            return
        row = item.row()
        command = toolListWidget.item(row, 2).data(QtCore.Qt.UserRole)
        checked = item.checkState() == QtCore.Qt.Checked
        toolListWidget.blockSignals(True)
        try:
            if checked:
                toolListWidget.item(row, 1 - item.column()).setCheckState(
                    QtCore.Qt.Unchecked)
        finally:
            toolListWidget.blockSignals(False)

        group = getGroup()
        commands = [value for value in group.GetString("ToolList").split(".,.") if value]
        outer = set(value for value in group.GetString("OuterToolList").split(".,.") if value)
        if checked:
            if command not in commands:
                commands.append(command)
            if item.column() == 1:
                outer.add(command)
            else:
                outer.discard(command)
        else:
            commands = [value for value in commands if value != command]
            outer.discard(command)
        group.SetString("ToolList", ".,.".join(commands))
        group.SetString("OuterToolList", ".,.".join(
            value for value in commands if value in outer))
        onShape(comboShape.currentText())
        buttonList()

    def searchInToolList(search_text):
        """Build the Inner / Outer command selectors using saved assignments."""
        search_text = search_text.lower()
        actionMapAll = getGuiActionMapAll()
        group = getGroup()
        selected = set(group.GetString("ToolList").split(".,."))
        outer = set(group.GetString("OuterToolList").split(".,."))
        toolListWidget.blockSignals(True)
        try:
            toolListWidget.clearContents()
            toolListWidget.setRowCount(0)
            for command, action in actionMapAll.items():
                action_text = action.text().replace("&", "")
                workbench = extractWorkbench(command) or ""
                if search_text not in action_text.lower() and search_text not in workbench.lower():
                    continue
                row = toolListWidget.rowCount()
                toolListWidget.insertRow(row)
                for column in (0, 1):
                    checkbox = QtGui.QTableWidgetItem()
                    checkbox.setFlags(
                        QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
                    checkbox.setTextAlignment(QtCore.Qt.AlignCenter)
                    assigned = command in selected and ((command in outer) == (column == 1))
                    checkbox.setCheckState(
                        QtCore.Qt.Checked if assigned else QtCore.Qt.Unchecked)
                    toolListWidget.setItem(row, column, checkbox)

                actionItem = QtWidgets.QTableWidgetItem(action_text)
                actionItem.setData(QtCore.Qt.UserRole, command)
                actionItem.setIcon(action.icon())
                actionItem.setFlags(QtCore.Qt.ItemIsEnabled)
                actionItem.setToolTip(action.toolTip())
                toolListWidget.setItem(row, 2, actionItem)

                label = "FreeCAD" if workbench == "Std" else (workbench or command)
                workbenchItem = QtGui.QTableWidgetItem(label)
                workbenchItem.setFlags(QtCore.Qt.ItemIsEnabled)
                toolListWidget.setItem(row, 3, workbenchItem)
        finally:
            toolListWidget.blockSignals(False)

    def buttonList2ToolList(buttonListWidget):
        """ add tool to list on button click """
        toolData = []
        rowCount = buttonListWidget.rowCount()

        for row in range(rowCount):
            item = buttonListWidget.item(row, 1)
            if (item.data(QtCore.Qt.UserRole)) is not None:
                toolData.append(item.data(QtCore.Qt.UserRole))
        group = getGroup()
        group.SetString("ToolList", ".,.".join(toolData))
        outer = set(group.GetString("OuterToolList").split(".,."))
        group.SetString("OuterToolList", ".,.".join(
            command for command in toolData if command in outer))

    def onButtonUp():
        """ Move up the selected tools in the list """
        selected_ranges = buttonListWidget.selectedRanges()
        if not selected_ranges:
            return

        selected_rows = set()
        for selection in selected_ranges:
            for row in range(selection.topRow(), selection.bottomRow() + 1):
                selected_rows.add(row)

        selected_rows = sorted(selected_rows)

        if 0 in selected_rows:
            return

        for row in selected_rows:
            item_first_column = buttonListWidget.takeItem(row, 0)
            item_second_column = buttonListWidget.takeItem(row, 1)

            buttonListWidget.removeRow(row)
            buttonListWidget.insertRow(row - 1)
            buttonListWidget.setItem(row - 1, 0, item_first_column)
            buttonListWidget.setItem(row - 1, 1, item_second_column)

        buttonList2ToolList(buttonListWidget)
        buttonList()

        for row in selected_rows:
            buttonListWidget.setRangeSelected(
                QtGui.QTableWidgetSelectionRange(row - 1, 0, row - 1, 1), True)

    def onButtonDown():
        """ Move down the selected tools in the list """
        selected_ranges = buttonListWidget.selectedRanges()

        if not selected_ranges:
            return

        selected_rows = set()
        for selection in selected_ranges:
            for row in range(selection.topRow(), selection.bottomRow() + 1):
                selected_rows.add(row)

        selected_rows = sorted(selected_rows, reverse=True)
        rowCount = buttonListWidget.rowCount()

        if rowCount - 1 in selected_rows:
            return

        for row in selected_rows:
            item_first_column = buttonListWidget.takeItem(row, 0)
            item_second_column = buttonListWidget.takeItem(row, 1)

            buttonListWidget.removeRow(row)
            buttonListWidget.insertRow(row + 1)
            buttonListWidget.setItem(row + 1, 0, item_first_column)
            buttonListWidget.setItem(row + 1, 1, item_second_column)

        buttonList2ToolList(buttonListWidget)
        buttonList()

        for row in selected_rows:
            buttonListWidget.setRangeSelected(
                QtGui.QTableWidgetSelectionRange(row + 1, 0, row + 1, 1), True)

    def onButtonRemoveCommand():
        """ Remove selected tools from the list """
        selected_ranges = buttonListWidget.selectedRanges()
        if not selected_ranges:
            return

        rows_to_remove = set()
        for selection in selected_ranges:
            for row in range(selection.topRow(), selection.bottomRow() + 1):
                rows_to_remove.add(row)

        for row in sorted(rows_to_remove, reverse=True):
            items = []
            for column in range(buttonListWidget.columnCount()):
                item = buttonListWidget.takeItem(row, column)
                items.append(item)

            buttonListWidget.removeRow(row)

        buttonListWidget.setFocus()
        buttonList2ToolList(buttonListWidget)
        buttonList()
        toolList()

        if rows_to_remove:
            last_removed_row = max(rows_to_remove)
            new_index = last_removed_row - len(rows_to_remove)
            if new_index >= 0:
                buttonListWidget.setCurrentCell(new_index, 1)

    def appendCommandToPieList(commandId):
        """ Append a command id to the ToolList of the pie selected in the combo box """
        indexList = getIndexList()
        for i in indexList:
            pie = getParamIndex(str(i))
            if pie == cBox.currentText():
                group = config.get_params()["index"].GetGroup(str(i))
                toolList = group.GetString("ToolList")
                if toolList:
                    toolList = toolList.split(".,.")
                else:
                    toolList = []
                toolList.append(commandId)
                group.SetString("ToolList", ".,.".join(toolList))

    def registerSeparatorAction():
        """ Create the plain QAction backing the PieMenu_Separator command.

        FreeCAD only materialises a command's QAction once the command is
        added to a menu or a toolbar, so with the hidden "PieMenuTB" hack
        gone the separator command resolves to nothing (see CHANGELOG 1.14).
        A configuration that still owns the toolbar already has an action,
        which is why an existing one is left untouched.

        \return The registered (or pre-existing) separator action.
        """
        mainWindow = Gui.getMainWindow()
        existingAction = mainWindow.findChild(QtGui.QAction, "PieMenu_Separator")
        if existingAction is not None:
            return existingAction

        action = QtGui.QAction(mainWindow)
        action.setObjectName("PieMenu_Separator")
        action.setText(translate('PieMenuTab', 'Separator'))
        action.setIcon(QtGui.QIcon(resources.iconAddSeparator))
        action.setToolTip(translate('PieMenuTab', 'Separator for PieMenu '))
        # parity with the command IsActive() == False: separators never trigger
        action.setEnabled(False)
        return action

    def getShortcutEntryNumbers():
        """ Return the list of stored shortcut entry numbers, may be empty """
        shortcutsGroup = App.ParamGet(
            "User parameter:BaseApp/PieMenu/Shortcuts")
        entryList = shortcutsGroup.GetString("EntryList")
        return [num for num in entryList.split(".,.") if num]

    def getShortcutEntryKey(actionId):
        """ Return the key sequence stored for a shortcut entry action """
        num = actionId[len(shortcutEntryPrefix):]
        shortcutsGroup = App.ParamGet(
            "User parameter:BaseApp/PieMenu/Shortcuts")
        return shortcutsGroup.GetGroup("Entry_" + num).GetString("Key")

    def getShortcutEntryIcon(iconPath):
        """ Resolve a stored shortcut entry icon value to something QIcon accepts """
        if iconPath:
            resolvedIcon = getIconPieMenu(iconPath)
            if not QtGui.QIcon(resolvedIcon).isNull():
                return resolvedIcon
        # a null icon would make getGuiActionMapAll() drop the action
        return resources.iconAddShortcut

    def formatKeySequence(keySequence):
        """ Return a human readable key sequence, or the raw text when unparseable """
        sequence = QKeySequence(keySequence)
        if sequence.isEmpty():
            return keySequence
        return sequence.toString(QKeySequence.PortableText)

    def registerShortcutEntryActions():
        """ Create or refresh the plain QAction of every stored shortcut entry """
        shortcutsGroup = App.ParamGet(
            "User parameter:BaseApp/PieMenu/Shortcuts")
        for num in getShortcutEntryNumbers():
            entryGroup = shortcutsGroup.GetGroup("Entry_" + num)
            actionId = shortcutEntryPrefix + num
            name = entryGroup.GetString(
                "Name") or translate("PieMenuTab", "Shortcut")
            key = entryGroup.GetString("Key")

            action = mw.findChild(QtGui.QAction, actionId)
            if action is None:
                action = QtGui.QAction(mw)
                action.setObjectName(actionId)
                # the handler re-reads the parameters, so edits need no reconnect
                action.triggered.connect(partial(triggerShortcutEntry, actionId))
            action.setText(name)
            # a null icon would make getGuiActionMapAll() drop the action
            action.setIcon(QtGui.QIcon(
                getShortcutEntryIcon(entryGroup.GetString("Icon"))))
            if key:
                action.setToolTip(f"{name} ({formatKeySequence(key)})")
            else:
                action.setToolTip(name)

    def triggerShortcutEntry(actionId, checked=None):
        """ Run the key sequence stored for a shortcut entry """
        num = actionId[len(shortcutEntryPrefix):]
        shortcutsGroup = App.ParamGet(
            "User parameter:BaseApp/PieMenu/Shortcuts")
        key = shortcutsGroup.GetGroup("Entry_" + num).GetString("Key")
        if not key:
            return
        # HoverButton hides the pie and focuses the main window right before
        # it fires the action, so the sequence is delivered on a later turn
        # of the event loop
        QtCore.QTimer.singleShot(50, partial(runShortcutSequence, key))

    def runShortcutSequence(keySequence):
        """ Execute a key sequence: an equally bound QAction wins, otherwise chords are replayed """
        target = QKeySequence(keySequence)
        if target.isEmpty():
            return
        targetText = target.toString(QKeySequence.PortableText).lower()

        # shortcut entries hold no QAction shortcut, so they never match themselves
        for action in mw.findChildren(QtGui.QAction):
            if action.shortcut().isEmpty() or not action.isEnabled():
                continue
            if action.shortcut().toString(QKeySequence.PortableText).lower() == targetText:
                action.trigger()
                return

        sendKeySequenceEvents(target)

    def sendKeySequenceEvents(sequence):
        """ Deliver a possibly multi-chord key sequence as key events to the focused widget """
        chords = sequence.toString(QKeySequence.PortableText).split(", ")
        receiver = QtWidgets.QApplication.focusWidget() or mw

        def sendChord(index):
            if index >= len(chords):
                return
            combination = QKeySequence(chords[index])[0]
            if hasattr(combination, "key"):
                # Qt6 returns a QKeyCombination
                key = combination.key()
                modifiers = combination.modifiers()
            else:
                # Qt5 packs the modifiers into the int
                raw = int(combination)
                key = raw & ~int(QtCore.Qt.KeyboardModifierMask)
                modifiers = QtCore.Qt.KeyboardModifiers(
                    raw & int(QtCore.Qt.KeyboardModifierMask))
            for event in (
                    QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, modifiers),
                    QtGui.QKeyEvent(QtCore.QEvent.KeyRelease, key, modifiers),
            ):
                QtWidgets.QApplication.sendEvent(receiver, event)
            if index + 1 < len(chords):
                QtCore.QTimer.singleShot(50, lambda: sendChord(index + 1))

        sendChord(0)

    def getSelectedShortcutEntryId():
        """ Return the id of the shortcut entry selected in the action list, if any """
        for selection in buttonListWidget.selectedRanges():
            for row in range(selection.topRow(), selection.bottomRow() + 1):
                item = buttonListWidget.item(row, 1)
                if item is None:
                    continue
                entryId = item.data(QtCore.Qt.UserRole)
                if entryId and str(entryId).startswith(shortcutEntryPrefix):
                    return str(entryId)
        return None

    def onButtonAddShortcut():
        """ Create a shortcut entry, or edit the one selected in the action list """
        showShortcutEntryDialog(getSelectedShortcutEntryId())

    def showShortcutEntryDialog(entryId=None):
        """ Dialog to create or edit a shortcut entry, a pie button that runs a key sequence """
        shortcutsGroup = App.ParamGet(
            "User parameter:BaseApp/PieMenu/Shortcuts")
        editing = entryId is not None
        if editing:
            num = entryId[len(shortcutEntryPrefix):]
            entryGroup = shortcutsGroup.GetGroup("Entry_" + num)
            initialName = entryGroup.GetString("Name")
            initialIcon = entryGroup.GetString("Icon")
            initialKey = entryGroup.GetString("Key")
        else:
            initialName = ""
            initialIcon = ""
            initialKey = ""

        chosenIcon = {"value": initialIcon}

        entry_form = load_form("ShortcutEditor.ui", pieMenuDialog,
                               (CustomLineEdit,), translate)
        dialog = entry_form.root
        nameEdit = entry_form.nameEdit
        iconButton = entry_form.iconButton
        shortcutEdit = entry_form.shortcutEdit
        dialogInfo = entry_form.dialogInfo
        clearShortcutButton = entry_form.clearShortcutButton
        buttonBox = entry_form.buttonBox
        if editing:
            dialog.setWindowTitle(translate("PieMenuTab", "Edit shortcut"))
        else:
            dialog.setWindowTitle(translate("PieMenuTab", "Add shortcut"))

        nameEdit.setText(initialName)
        iconButton.setIcon(QtGui.QIcon(getShortcutEntryIcon(initialIcon)))

        shortcutEdit.setText(initialKey)
        # the shared line edit warns in the pie settings label by default
        shortcutEdit.warningLabel = dialogInfo

        clearShortcutButton.setIcon(
            QtGui.QIcon.fromTheme(resources.iconBackspace))
        clearShortcutButton.clicked.connect(shortcutEdit.clear)

        def applyChosenIcon(iconValue):
            chosenIcon["value"] = iconValue
            iconButton.setIcon(QtGui.QIcon(getShortcutEntryIcon(iconValue)))

        def pickIconForEntry():
            iconPickerTarget["setIcon"] = applyChosenIcon
            iconPickerTarget["parent"] = dialog
            onButtonIconPieMenu()

        def onValidate():
            name = nameEdit.text().strip() or translate(
                "PieMenuTab", "Shortcut")
            key = shortcutEdit.text().strip()
            if not key:
                dialogInfo.setText(
                    translate("PieMenuTab", "Please assign a shortcut"))
                return
            if QKeySequence(key).isEmpty():
                dialogInfo.setText(translate("PieMenuTab", "Invalid shortcut"))
                return

            if editing:
                entryGroup.SetString("Name", name)
                entryGroup.SetString("Icon", chosenIcon["value"])
                entryGroup.SetString("Key", key)
            else:
                nextNum = shortcutsGroup.GetInt("NextId")
                if nextNum < 1:
                    nextNum = 1
                newNum = str(nextNum)
                shortcutsGroup.SetInt("NextId", nextNum + 1)
                newGroup = shortcutsGroup.GetGroup("Entry_" + newNum)
                newGroup.SetString("Name", name)
                newGroup.SetString("Icon", chosenIcon["value"])
                newGroup.SetString("Key", key)
                entryNumbers = getShortcutEntryNumbers()
                entryNumbers.append(newNum)
                shortcutsGroup.SetString("EntryList", ".,.".join(entryNumbers))
                appendCommandToPieList(shortcutEntryPrefix + newNum)
            App.saveParameter()
            registerShortcutEntryActions()
            buttonList()
            toolList()
            dialog.accept()

        def releaseIconPicker(_result):
            # detach the shared icon picker before the dialog goes away
            iconPickerTarget["setIcon"] = None
            iconPickerTarget["parent"] = None
            window_icons.setParent(pieMenuDialog)

        dialog.finished.connect(releaseIconPicker)
        iconButton.clicked.connect(lambda checked=False: pickIconForEntry())
        nameEdit.returnPressed.connect(onValidate)

        buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setText(
            translate("PieMenuTab", "Validate"))
        buttonBox.button(QtWidgets.QDialogButtonBox.Cancel).setText(
            translate("PieMenuTab", "Cancel"))
        buttonBox.accepted.connect(onValidate)
        buttonBox.rejected.connect(dialog.reject)

        dialog.exec()

    def onButtonAddSeparator():
        """ Handle separator for PieMenus """
        # The hidden "PieMenuTB" toolbar is no longer created here: writing
        # 'Name = PieMenuTB' into BaseApp/Workbench/Global/Toolbar/Custom_PieMenu
        # made it appear in the toolbar configuration. The original block stays
        # commented out as a reference for older setups (see CHANGELOG 1.14).
        # we must create a custom toolbar "PieMenuTB" to 'activate' the command 'PieMenu_Separator' otherwise the separators are not correctly handled
        # globaltoolbar = App.ParamGet(
        #     'User parameter:BaseApp/Workbench/Global/Toolbar/Custom_PieMenu')
        #
        # pieMenuTB = globaltoolbar.GetString('Name')
        # if pieMenuTB == "PieMenuTB":
        #     pass
        # else:
        #     globaltoolbar.SetString('Name', 'PieMenuTB')
        #     App.saveParameter()
        #
        # globaltoolbar.SetString('PieMenu_Separator', 'FreeCAD')

        # no workbench reload is needed anymore: registerSeparatorAction()
        # created the plain action once at start-up

        # we hide the custom toolbar
        mw = Gui.getMainWindow()
        for i in mw.findChildren(QtGui.QToolBar):
            if i.windowTitle() == 'PieMenuTB':
                i.setVisible(False)

        appendCommandToPieList("PieMenu_Separator")
        buttonList()

    def onButtonToolBar():
        """ Show interface to add existing Freecad's Toolbars """
        infoShortcut.setText('')
        piemenuBoxGroup.setVisible(False)

        tabs.setVisible(False)
        toolBarTab.setVisible(True)
        buttonBackToSettings.setVisible(True)
        buttonExistingToolBar.setVisible(False)

        for i in reversed(range(buttonsLayout.count())):
            try:
                buttonsLayout.itemAt(i).widget().hide()
            except:
                None
            # hide shortcuts in buttonListWidget
            buttonListWidget.setColumnHidden(0, True)

        # generate list of existing toolBars
        listToolBar = onListToolBar()

        # set first element of listToolBar
        index = listToolBar.model().index(0, 0)
        if index.isValid():
            listToolBar.setCurrentIndex(index)
        showListToolBar()

        updatePiemenuPreview("toolBarTab")

    def onBackToSettings():
        """ Return to general settings interface """
        toolBarTab.setVisible(False)
        piemenuBoxGroup.setVisible(True)
        buttonExistingToolBar.setVisible(True)
        for i in reversed(range(buttonsLayout.count())):
            try:
                buttonsLayout.itemAt(i).widget().show()
            except:
                None
        tabs.setVisible(True)

        vSplitter.refresh()
        buttonBackToSettings.setVisible(False)
        onPieChange()
        updatePiemenuPreview()

    def onParamExport():
        """ Export parameter to a file """
        file, _ = QFileDialog.getSaveFileName(None, translate(
            "ExportSettingsWindow", "Export PieMenu settings to a file"), "", "XML (*.FCParam)")
        if file:
            try:
                if not file.endswith(".FCParam"):
                    file += ".FCParam"
                item = App.ParamGet("User parameter:BaseApp/PieMenu")
                item.Export(file)

                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setText(translate("GlobalSettingsTab",
                            "PieMenu settings exported successfully."))
                msg.setWindowTitle(
                    translate("GlobalSettingsTab", "Information"))
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec()

            except Exception as e:
                print(f"Error exporting settings: {str(e)}")

    def onParamImport():
        """Import parameter from a file"""
        configDir = App.getUserConfigDir()
        configDir = configDir.replace("\\", "/")
        userConfigFile = os.path.join(configDir, "user.cfg")

        backupDir = os.path.join(configDir, "user_config_backup")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backupFile = os.path.join(backupDir, f"user_backup_{timestamp}.cfg")

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Question)
        msg.setText(translate("GlobalSettingsTab",
                    "Before importing settings a backup of the current user configuration file (user.cfg) will be saved."))
        msg.setInformativeText(
            translate("GlobalSettingsTab", "Do you want to continue?"))
        msg.setWindowTitle(
            translate("GlobalSettingsTab", "Backup user settings"))
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.Yes)
        response = msg.exec()

        if response == QMessageBox.Yes:
            if not os.path.exists(backupDir):
                os.makedirs(backupDir)

            try:
                shutil.copy(userConfigFile, backupFile)
                print(f"Backup of configuration file created at {backupFile}")
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setText(
                    translate(
                        "GlobalSettingsTab",
                        "Backup of the current user configuration file successfully saved in: {}",
                    ).format(backupFile)
                )
                msg.setInformativeText(
                    translate(
                        "GlobalSettingsTab",
                        "Click OK to select the file to import PieMenu settings.",
                    )
                )
                msg.setWindowTitle(
                    translate("GlobalSettingsTab", "Successful backup"))
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec()

                file, _ = QFileDialog.getOpenFileName(None, translate(
                    "ImportSettingsWindow", "Import PieMenu settings from a file"), "", "XML (*.FCParam)")

                if file:
                    try:
                        item = App.ParamGet("User parameter:BaseApp/PieMenu")
                        item.Import(file)

                        msg = QMessageBox()
                        msg.setIcon(QMessageBox.Information)
                        msg.setText(translate("RestartFreeCADWindow",
                                    "PieMenu settings imported successfully."))
                        msg.setInformativeText(translate(
                            "RestartFreeCADWindow", "Please restart FreeCAD for changes to take effect. \nRestart FreeCAD ?"))
                        msg.setWindowTitle(
                            translate("RestartFreeCADWindow", "Restart Required"))
                        msg.setStandardButtons(
                            QMessageBox.Yes | QMessageBox.No)

                        nowButton = msg.button(QMessageBox.Yes)
                        nowButton.setText(
                            translate("RestartFreeCADWindow", "Now"))
                        laterButton = msg.button(QMessageBox.No)
                        laterButton.setText(
                            translate("RestartFreeCADWindow", "Later"))
                        response = msg.exec()

                        if response == QMessageBox.Yes:
                            """Shuts down and restarts FreeCAD"""
                            args = QtWidgets.QApplication.arguments()[1:]
                            if Gui.getMainWindow().close():
                                QtCore.QProcess.startDetached(
                                    QtWidgets.QApplication.applicationFilePath(), args
                                )

                    except Exception as e:
                        print(f"Error importing parameters: {str(e)}")
                    return True

            except Exception as e:
                print(f"Error creating backup: {str(e)}")
                return  # Exit the function if backup fails
        else:
            return False

    def comboBox(TopoType):
        """ Set combobox for context conditions """
        signList = ["<", "<=", "==", "!=", ">", ">="]
        model = QtGui.QStandardItemModel()
        for i in signList:
            item = QtGui.QStandardItem()
            item.setText(i)
            item.setData(TopoType, QtCore.Qt.UserRole)
            model.setItem(signList.index(i), 0, item)
        comboBoxSign = QtGui.QComboBox()
        comboBoxSign.setObjectName("styleCombo")
        comboBoxSign.setModel(model)
        styleCurrentTheme = getStyle()
        comboBoxSign.setStyleSheet(styleCurrentTheme)

        def onCurrentIndexChanged():
            if state.app_state.sub_group_selected:
                group = getGroup()
                groupContext = group.GetGroup(state.app_state.sub_group_selected)
                text = comboBoxSign.currentText()
                topo = comboBoxSign.itemData(comboBoxSign.currentIndex(),
                                             QtCore.Qt.UserRole)
                groupContext.SetString(topo, text)
                contextList()
                updateContextConditions()
                infoShortcut.setText("")
            else:
                updateInfoShortcut()

        comboBoxSign.currentIndexChanged.connect(onCurrentIndexChanged)
        return comboBoxSign

    def spinBox(TopoValue):
        """ Spinbox in context tab """
        spinBox = QtGui.QSpinBox()
        spinBox.setFrame(False)

        def onSpinBox():
            if state.app_state.sub_group_selected:
                group = getGroup()
                groupContext = group.GetGroup(state.app_state.sub_group_selected)
                value = spinBox.value()
                groupContext.SetInt(TopoValue, value)
                contextList()
                updateContextConditions()
                infoShortcut.setText("")
            else:
                updateInfoShortcut()

        spinBox.valueChanged.connect(onSpinBox)
        return spinBox

    def updateInfoShortcut():
        infoShortcut.setText(translate(
            "ContextTab", "Select an existing rule to modify it or create a new one."))

    def onAddContextConditions(subgroup=None):
        """ Add new context rule in context Tab """
        indexList = getIndexList()
        numGroup = 0
        for i in indexList:
            pieName = getParamIndex(str(i))
            if pieName == cBox.currentText():
                group = config.get_params()["index"].GetGroup(str(i))
                contexts = ["Context", "Context2", "Context3", "Context4"]
                for subGroup in contexts:
                    groupContext = group.GetGroup(subGroup)
                    groupContents = groupContext.GetContents()
                    if groupContents:
                        numGroup += 1
                    else:
                        infoShortcut.setText('')
                        groupContext.SetString(
                            "VertexSign", vertexComboBox.currentText())
                        groupContext.SetString(
                            "EdgeSign", edgeComboBox.currentText())
                        groupContext.SetString(
                            "FaceSign", faceComboBox.currentText())
                        groupContext.SetString(
                            "ObjectSign", objectComboBox.currentText())
                        groupContext.SetString(
                            "AxisSign", axisComboBox.currentText())
                        groupContext.SetString(
                            "PlaneSign", planeComboBox.currentText())

                        groupContext.SetInt("VertexValue", vertexSpin.value())
                        groupContext.SetInt("EdgeValue", edgeSpin.value())
                        groupContext.SetInt("FaceValue", faceSpin.value())
                        groupContext.SetInt("ObjectValue", objectSpin.value())
                        groupContext.SetInt("AxisValue", axisSpin.value())
                        groupContext.SetInt("PlaneValue", planeSpin.value())

                        groupContext.SetBool("Enabled", 1)

                        updateContextConditions()
                        break

    def onDelContextConditions(subgroup=None):
        """ Delete a context rule """
        if subgroup:
            indexList = getIndexList()
            for index in indexList:
                pieName = getParamIndex(str(index))
                if pieName == cBox.currentText():
                    group = config.get_params()["index"].GetGroup(str(index))
                    if group.GetGroup(subgroup):
                        group.RemGroup(subgroup)
                        # workaround to refresh the window to avoid bug https://github.com/Grubuntu/PieMenu/issues/125
                        pieMenuDialog.close()
                        pieMenuDialog.show()

    def updateContextConditions():
        """ Update context rules in Context Tab """

        indexList = getIndexList()
        selectedPie = cBox.currentText()

        # Efface les anciennes données du tableau
        listContextConditions.setUpdatesEnabled(False)
        listContextConditions.setRowCount(0)

        state.app_state.row_subgroup_map.clear()
        row = -1
        for index in indexList:
            pieName = getParamIndex(str(index))
            if pieName == selectedPie:
                group = config.get_params()["index"].GetGroup(str(index))
                if not group:
                    continue  # Skip if group is invalid

                subgroups = group.GetGroups()
                if not subgroups:
                    continue  # Skip if no subgroups found

                for subGroup in subgroups:
                    groupContext = group.GetGroup(subGroup)
                    groupContents = groupContext.GetContents()
                    if groupContents:
                        row = listContextConditions.rowCount()
                        listContextConditions.insertRow(row)

                        # Add checkbox for enabling/disabling
                        subgroupContextEnabled = QCheckBox(
                            translate("ContextTab", ""))
                        subgroupContextEnabled.setCheckable(True)
                        subgroupContextEnabled.setToolTip(translate(
                            "ContextTab", "Ticked the box to enable the contextual rule."))

                        subgroupContextEnabled.setChecked(
                            groupContext.GetBool("Enabled"))
                        subgroupContextEnabled.stateChanged.connect(
                            lambda state, group=group, subGroup=subGroup: onContextEnabled(
                                state, group, subGroup)
                        )
                        listContextConditions.setCellWidget(
                            row, 0, subgroupContextEnabled)

                        # Add condition description
                        conditionItem = QtGui.QTableWidgetItem(
                            parseContextConditions(subGroup))
                        conditionItem.setTextAlignment(
                            Qt.AlignLeft | Qt.AlignVCenter)
                        conditionItem.setFlags(
                            Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                        conditionItem.setToolTip(
                            translate("ContextTab", "Select a rule to modify it. If the rule is active and the selection matches the criteria chosen, this PieMenu will open."))
                        listContextConditions.setItem(row, 1, conditionItem)

                        # Add remove button
                        buttonRemoveCondition = QtGui.QToolButton()
                        buttonRemoveCondition.setIcon(QtGui.QIcon(resources.iconRemove))
                        buttonRemoveCondition.setIconSize(QtCore.QSize(18, 18))
                        buttonRemoveCondition.setToolTip(
                            translate("ContextTab", "Delete this rule"))
                        buttonRemoveCondition.clicked.connect(
                            partial(onDelContextConditions, subGroup))
                        listContextConditions.setCellWidget(
                            row, 2, buttonRemoveCondition)

                        # Map the row number to subGroup
                        state.app_state.row_subgroup_map[row] = subGroup

                        # Mettre en gras si le subGroup correspond au state.app_state.sub_group_selected global
                        if state.app_state.sub_group_selected == subGroup:
                            for c in range(listContextConditions.columnCount()):
                                item = listContextConditions.item(row, c)
                                if item:
                                    font = item.font()
                                    font.setBold(True)  # Appliquer le gras
                                    item.setFont(font)

        labelListContext.setText(
            translate("ContextTab", "List of current selection rules: {}/4").format(row+1))

        # Disable ability to add new rule when max (4) is reached (row : 0,1,2,3)
        if row > 2:
            addContextConditions.setEnabled(False)
        else:
            addContextConditions.setEnabled(True)

        listContextConditions.setUpdatesEnabled(True)

    def onRowSelected():
        """ Update values in comboboxes and spinboxes according to selected rule """
        selectedItems = listContextConditions.currentItem()
        if not selectedItems:
            return

        row = selectedItems.row()  # Récupère la ligne sélectionnée
        subGroup = state.app_state.row_subgroup_map.get(row)  # Récupère le subGroup associé

        # if already selectd, we deselect it
        if subGroup == state.app_state.sub_group_selected:
            onClearContextSelection()
        else:
            state.app_state.sub_group_selected = subGroup
            if subGroup:
                indexList = getIndexList()
                group = None
                # Trouve le groupe associé à la sélection
                for i in indexList:
                    pieName = getParamIndex(str(i))
                    if pieName == cBox.currentText():
                        group = config.get_params()["index"].GetGroup(str(i))
                        break

                if group:
                    groupContext = group.GetGroup(subGroup)
                    # Mise à jour des combobox et spinbox
                    updateComboBox(
                        vertexComboBox, groupContext.GetString("VertexSign"))
                    vertexSpin.setValue(groupContext.GetInt("VertexValue"))
                    updateComboBox(
                        edgeComboBox, groupContext.GetString("EdgeSign"))
                    edgeSpin.setValue(groupContext.GetInt("EdgeValue"))
                    updateComboBox(
                        faceComboBox, groupContext.GetString("FaceSign"))
                    faceSpin.setValue(groupContext.GetInt("FaceValue"))
                    updateComboBox(
                        objectComboBox, groupContext.GetString("ObjectSign"))
                    objectSpin.setValue(groupContext.GetInt("ObjectValue"))
                    updateComboBox(
                        axisComboBox, groupContext.GetString("AxisSign"))
                    axisSpin.setValue(groupContext.GetInt("AxisValue"))
                    updateComboBox(
                        planeComboBox, groupContext.GetString("PlaneSign"))
                    planeSpin.setValue(groupContext.GetInt("PlaneValue"))

                updateContextConditions()

    def updateComboBox(comboBox, value):
        """Met à jour la sélection d'une combobox avec une valeur donnée."""
        index = comboBox.findText(value)
        if index != -1:
            comboBox.setCurrentIndex(index)

    def onContextEnabled(state, group, subGroup):
        """ Update 'Enabled' parameter when checkboxstate change """
        groupContext = group.GetGroup(subGroup)
        if state == 2:
            groupContext.SetBool("Enabled", 1)
        else:
            groupContext.SetBool("Enabled", 0)

    def parseContextConditions(subGroup=None):
        """ Generates the String representing the context rule conditions """
        indexList = getIndexList()
        for i in indexList:
            pieName = getParamIndex(str(i))
            if pieName == cBox.currentText():
                group = config.get_params()["index"].GetGroup(str(i))
                if subGroup:
                    a = group.GetGroup(subGroup)
                    liste = a.GetContents()

                    signs = {}
                    values = {}

                    if liste:
                        # Remplir les dictionnaires
                        for item in liste:
                            if item[0] == 'String':
                                # Sauvegarder les éléments de type String (nom + signe)
                                # Suppression de 'Sign' pour obtenir juste le nom
                                key = item[1].replace('Sign', '')
                                # Ici on récupère le signe
                                signs[key] = item[2]
                            elif item[0] == 'Integer':
                                # Sauvegarder les valeurs
                                # Suppression de 'Value' pour obtenir juste le nom
                                key = item[1].replace('Value', '')
                                values[key] = item[2]

                    # Construction de la chaîne de texte finale
                    result = ', '.join(
                        f"{key} {signs[key]} {values[key]}" for key in signs)
        return result

    def onClearContextSelection():
        """ Clear the selection in the list of rules """
        state.app_state.sub_group_selected = None
        updateContextConditions()

    def onResetContextTable():
        """ Reset combobox and spinbox values in context tab """
        group = getGroup()
        if state.app_state.sub_group_selected:
            groupContext = group.GetGroup(state.app_state.sub_group_selected)
            groupContext.SetBool("Enabled", 0)

        # Initialisation des combobox et spinbox
        updateComboBox(vertexComboBox, "==")
        vertexSpin.setValue(10)
        updateComboBox(edgeComboBox, "==")
        edgeSpin.setValue(10)
        updateComboBox(faceComboBox, "==")
        faceSpin.setValue(10)
        updateComboBox(objectComboBox, "==")
        objectSpin.setValue(10)
        updateComboBox(axisComboBox, "==")
        axisSpin.setValue(10)
        updateComboBox(planeComboBox, "==")
        planeSpin.setValue(10)
        updateContextConditions()

    def setContextConditions():
        """Initializes the context conditions depending on parameters."""
        def update_sign(group_context, key, combo_box, default="=="):
            """Update the sign value and set the combo box index."""
            sign_value = group_context.GetString(key)
            if sign_value not in sign:
                group_context.SetString(key, default)
                sign_value = default
            for i in range(combo_box.count()):
                if combo_box.itemText(i) == sign_value:
                    combo_box.setCurrentIndex(i)
                    break

        def update_value(group_context, key, spin_box, default=10):
            """Update the value and set the spin box."""
            value = group_context.GetInt(key)
            if not value:
                a = group_context.GetInt(key, True)
                b = group_context.GetInt(key, False)
                value = 0 if a == b else default
                group_context.SetInt(key, value)
            spin_box.setValue(value)

        index_list = getIndexList()
        contexts = ["Context", "Context2", "Context3", "Context4"]

        for i in index_list:
            group = config.get_params()["index"].GetGroup(str(i))
            for sub_group in contexts:
                group_context = group.GetGroup(sub_group)
                group_contents = group_context.GetContents()

                if group_contents:
                    enabled = group_context.GetBools()
                    if enabled:
                        break
                    else:
                        group_context.SetBool("Enabled", 0)

                    # Update signs and values for each component
                    update_sign(group_context, "VertexSign", vertexComboBox)
                    update_value(group_context, "VertexValue", vertexSpin)
                    update_sign(group_context, "EdgeSign", edgeComboBox)
                    update_value(group_context, "EdgeValue", edgeSpin)
                    update_sign(group_context, "FaceSign", faceComboBox)
                    update_value(group_context, "FaceValue", faceSpin)
                    update_sign(group_context, "ObjectSign", objectComboBox)
                    update_value(group_context, "ObjectValue", objectSpin)
                    update_sign(group_context, "AxisSign", axisComboBox)
                    update_value(group_context, "AxisValue", axisSpin)
                    update_sign(group_context, "PlaneSign", planeComboBox)
                    update_value(group_context, "PlaneValue", planeSpin)
        contextList()

    def setDefaultPie(restore=False):
        """ Initialize the defaults PieMenus if needed """
        indexList = getIndexList()
        if 0 in indexList:
            if restore:
                group = config.get_params()["index"].GetGroup("0")
                # TODO: scan for `defaultTools` and notices that it might be worth inlining
                group.SetString("ToolList", ".,.".join(constants.defaultTools))
            else:
                pass
        else:
            defaultPies = (
                (0, "View", constants.defaultTools),
                (1, "PartDesign", constants.defaultToolsPartDesign),
                (2, "Sketcher", constants.defaultToolsSketcher),
            )

            for defaultIndex, defaultName, defaultTools in defaultPies:
                if defaultIndex in indexList:
                    continue
                indexList.append(defaultIndex)
                config.get_params()["index"].SetString(
                    str(defaultIndex), defaultName)
                group = config.get_params()["index"].GetGroup(
                    str(defaultIndex))
                group.SetString("ToolList", ".,.".join(defaultTools))
                setDefaultValues(group)
                if defaultIndex == 2:
                    group.SetString("DefaultWorkbench", "Sketcher")

            indexList = [str(i) for i in indexList]
            config.get_params()["index"].SetString(
                "IndexList", ".,.".join(indexList))

        config.get_params()["main"].SetBool("ToolBar", False)
        config.get_params()["main"].RemString("ToolBar")
        config.get_params()["main"].SetString("CurrentPie", "View")
        config.get_params()["main"].SetString("Theme", "Legacy")
        config.get_params()["main"].SetString("GlobalShortcutKey", "TAB")
        config.get_params()["main"].SetBool("ShowQuickMenu", True)
        config.get_params()["main"].SetBool("DisplaySpinBox", True)
        config.get_params()["main"].SetBool("EnableContext", False)
        config.get_params()["main"].SetBool("GlobalKeyToggle", True)
        config.get_params()["main"].SetInt("DelayRightClick", 100)
        App.saveParameter()

    def onIconClicked(objIcon):
        """ Set icon to the PieMenu """
        # while the shortcut entry dialog owns the picker, hand the icon to it
        setIconFromPicker = iconPickerTarget["setIcon"]
        if setIconFromPicker is not None:
            iconPickerTarget["setIcon"] = None
            window_icons.close()
            setIconFromPicker(objIcon)
            return

        indexList = getIndexList()
        for i in indexList:
            pieName = getParamIndex(str(i))
            if pieName == cBox.currentText():
                param = config.get_params()["index"].GetGroup(str(i))
                param.SetString("IconPath", objIcon)

        commandName = 'PieMenu_' + cBox.currentText()
        all_actions = Gui.getMainWindow().findChildren(QtGui.QAction)

        for action in all_actions:
            if action.data() == commandName:
                icon = getIconPieMenu(objIcon)
                action.setIcon(QtGui.QIcon(icon))

        window_icons.close()
        updateIconsPieMenus()
        toolList()
        onPieChange()

    def onButtonBrowseIcon():
        """ Open dialog to browse files to choose an icon """
        window_icons.close()
        file_path, _ = QFileDialog.getOpenFileName(
            None, "Choose Icon", "", "SVG Files (*.svg);;ICO Files (*.ico);;All files (*.*)")

        if file_path:
            setIconFromPicker = iconPickerTarget["setIcon"]
            if setIconFromPicker is not None:
                iconPickerTarget["setIcon"] = None
                setIconFromPicker(file_path)
                return

            indexList = getIndexList()
            for i in indexList:
                pieName = getParamIndex(str(i))
                if pieName == cBox.currentText():
                    param = config.get_params()["index"].GetGroup(str(i))
                    param.SetString("IconPath", file_path)
                    buttonIconPieMenu.setIcon(QtGui.QIcon(file_path))

            globaltoolbar = App.ParamGet(
                'User parameter:BaseApp/Workbench/Global/Toolbar/Custom_PieMenu')
            globaltoolbar.SetString('PieMenu_' + pieName, 'FreeCAD')

            updateIconsPieMenus()
            toolList()
            onPieChange()
            pieMenuDialog.show()

    def onButtonIconPieMenu():
        """ Create and show the list of available icons for PieMenu icon """
        # purge leftovers: onIconClicked() closes the window without purging
        while grid_layout.count() > 0:
            item = grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        row, col = 0, 0
        icons_list = getAllActions()

        # add default icon PieMenuLogo at beginning of the list
        buttonIcon = QtGui.QToolButton()
        buttonIcon.setIcon(QtGui.QIcon(resources.iconPieMenuLogo))
        buttonIcon.setIconSize(QtCore.QSize(24, 24))
        buttonIcon.setObjectName("styleButtonMenu")
        buttonIcon.setToolTip("Default PieMenuLogo")
        grid_layout.addWidget(buttonIcon, row, col)
        buttonIcon.clicked.connect(partial(onIconClicked, resources.iconPieMenuLogo))
        col += 1

        for action in icons_list:
            if action.data() is not None and isinstance(action.data(), str):
                buttonIcon = QtGui.QToolButton()
                buttonIcon.setIcon(QtGui.QIcon(action.icon()))
                buttonIcon.setIconSize(QtCore.QSize(24, 24))
                buttonIcon.setObjectName("styleButtonMenu")
                buttonIcon.setToolTip(action.data())
                grid_layout.addWidget(buttonIcon, row, col)
                buttonIcon.clicked.connect(
                    partial(onIconClicked, action.data()))
                col += 1
                if col >= 8:
                    col = 0
                    row += 1

        # the entry dialog is application modal: its child window stays
        # interactive while any other parent would be blocked by exec()
        window_icons.setParent(iconPickerTarget["parent"] or pieMenuDialog)
        window_icons.setWindowTitle(translate("PieMenuTab", "Choose Icon"))
        window_icons.setWindowFlags(
            QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.X11BypassWindowManagerHint)

        window_icons.setWindowModality(QtCore.Qt.ApplicationModal)

        pieMenuDialogPos = pieMenuDialog.pos()
        posX = pieMenuDialogPos.x() + pieMenuDialog.width()/2 - pieMenuDialog.width()/4
        posY = pieMenuDialogPos.y() + pieMenuDialog.height()/3
        window_icons.setGeometry(
            posX, posY, pieMenuDialog.width()/2, pieMenuDialog.height()/2)
        window_icons.show()

    def window_icons_close():
        """ Close the window and purge the grid """
        # the picker was abandoned: the entry dialog icon stays untouched
        iconPickerTarget["setIcon"] = None
        iconPickerTarget["parent"] = None

        # grid purge is needed
        while grid_layout.count() > 0:
            item = grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        window_icons.close()
        pieMenuDialog.show()

    def legacyFix():
        """ Routine to fix old code """
        # Since v1.10 : "Std_PieMenu_" replace by "PieMenu_" to comply with WB naming
        indexList = getIndexList()
        for i in indexList:
            pie = getParamIndex(str(i))
            group = config.get_params()["index"].GetGroup(str(i))
            toolList = getParameterGroup(pie, "String", "ToolList")

            if "Std_PieMenu_" in toolList:
                toolList = toolList.replace("Std_PieMenu_", "PieMenu_")
                group.SetString("ToolList", toolList)

            if 'Std_PieMenuSeparator' in toolList:
                toolList = toolList.replace(
                    "Std_PieMenuSeparator", "PieMenu_Separator")
                group.SetString("ToolList", toolList)
                
        # v1.12: Introduce a new setting to choose whether to show the fast spinbox or not. Set the default value to True if the setting does not exist
        settingContent = config.get_params()["main"].GetContents()
        if not any(item[1] == "DisplaySpinBox" for item in settingContent):
            config.get_params()["main"].SetBool("DisplaySpinBox", True)

    #### Preferences dialog ####
    def onControl(keyValue=None):
        """Initializes the preferences dialog."""
        if keyValue is None or keyValue == "toolBarTab":
            wb = Gui.activeWorkbench()
            wbName = wb.name()
            wbName = wbName.replace("Workbench", "")
            keyValue = getPieName(wbName)

        if keyValue is None:
            keyValue = getParam("CurrentPie")

        cBoxUpdate(keyValue)

        buttonList()
        tabs.setCurrentIndex(0)

        # Reuse the settings dialog: the event filter retains its child widgets.
        labelGlobalShortcut.setText(
            translate("GlobalSettingsTab", "Global shortcut: ") + state.app_state.global_shortcut_key)

        pieMenuDialog.show()
        shape = getShape(cBox.currentText())
        onShape(shape)
        updateIconsPieMenus()
        updatePiemenuPreview()
        #### END Preferences dialog ####

    ### Begin QuickMenu  Def ###
    def quickMenu(buttonSize=20):
        """Build and style the QuickMenu button."""

        def pieList():
            """Populate the menuPieMenu with actions based on user parameters."""
            indexList = getIndexList()
            menuPieMenu.clear()

            pieList = []
            shortlist = []
            for i in indexList:
                pieName = getParamIndex(str(i))
                pieList.append(pieName)
                param = config.get_params()["index"].GetGroup(str(i))
                shortcut = param.GetString("ShortcutKey")
                shortlist.append(shortcut)
            if not config.get_params()["main"].GetBool("ToolBar"):
                text = getParam("CurrentPie")
            else:
                text = None

            for i, pieName in enumerate(pieList):
                action = QtGui.QAction(pieGroup)
                if i < len(shortlist):
                    shortcut = shortlist[i]
                    action.setText(f"{pieName}")
                    action.setShortcut(QtGui.QKeySequence(shortcut))
                    action.setCheckable(True)
                    if pieName == text:
                        action.setChecked(True)
                        # Add icon in front of default PieMenu in Quickmenu list
                        action.setIcon(iconDefault)
                else:
                    pass
                menuPieMenu.addAction(action)

        def onPieGroup():
            """Handle the default pieMenu selection event in quickMenu."""
            config.get_params()["main"].SetBool("ToolBar", False)
            config.get_params()["main"].RemString("ToolBar")
            try:
                text = pieGroup.checkedAction().text().encode("UTF-8")
                config.get_params()["main"].SetString("CurrentPie", text)
            except TypeError:
                text = pieGroup.checkedAction().text()
                config.get_params()["main"].SetString("CurrentPie", text)
            PieMenuInstance.hide()
            PieMenuInstance.showAtMouseInstance()

        def onMenuToolBar():
            """Handle the toolbar menu setup event."""
            menuToolBar.clear()
            if config.get_params()["main"].GetBool("ToolBar"):
                text = config.get_params()["main"].GetString("ToolBar")
                if ": " in text:
                    toolbar_desc = text.split(": ")
                    text = toolbar_desc[1]
                else:
                    pass
            else:
                text = None
            for i in mw.findChildren(QtGui.QToolBar):
                commands = []
                for a in i.findChildren(QtGui.QToolButton):
                    try:
                        if not a.defaultAction().isSeparator():
                            commands.append(a.defaultAction())
                        else:
                            pass
                    except AttributeError:
                        pass
                if len(commands) != 0:
                    menu = QtGui.QMenu(i.windowTitle())
                    menu.aboutToShow.connect(lambda sender=menu:
                                             onMenuToolbarGroup(sender))
                    menuToolBar.addMenu(menu)
                else:
                    pass

        def isActualPie(text):
            """Check if the given text corresponds to the current toolbar (or menu)."""
            if config.get_params()["main"].GetBool("ToolBar"):
                entry = config.get_params()["main"].GetString("ToolBar")
                if ": " in entry:
                    toolbar_desc = entry.split(": ")
                    idMenu = toolbar_desc[1]
                else:
                    idMenu = entry
                if idMenu == text:
                    return True
            return False

        def onMenuToolbarGroup(sender):
            """Handle the toolbar menu group setup event."""
            if not sender.actions():
                action = QtGui.QAction(sender)
                action.setText("Show")
                action.setData(sender.title())
                action.setCheckable(True)
                if isActualPie(sender.title()):
                    action.setChecked(True)
                sender.addAction(action)
                action = QtGui.QAction(sender)
                action.setText("Save")
                action.setData(sender.title())
                sender.addAction(action)
                sender.triggered.connect(lambda sender: onToolbarGroup(sender))

        def onToolbarGroup(sender):
            """Handle actions triggered in response to a toolbar menu."""
            if sender.text() == "Show":
                config.get_params()["main"].SetBool("ToolBar", True)
            elif sender.text() == "Save":
                newPieGroup = createPie(sender.data())
            else:
                return
            workbenches = []
            commands = []
            if sender.text() == "Save":
                # write persistent commands
                getGuiToolButtonData(sender.data(), None, commands, None)
                newPieGroup.SetString("ToolList", ".,.".join(commands))
                newPieGroup.SetString("Shape", "Pie")
            elif sender.text() == "Show":
                # write persistent toolbar and its workbenches
                getGuiToolButtonData(sender.data(), None, None, workbenches)
                toolbar_desc = ", ".join(workbenches)
                toolbar_desc = toolbar_desc + ': ' + sender.data()
                config.get_params()["main"].SetString("ToolBar", toolbar_desc)
                PieMenuInstance.hide()
                PieMenuInstance.showAtMouseInstance()

        def onPrefButton():
            """Handle the preferences button event."""
            PieMenuInstance.hide()
            onControl()

        #### QuickMenu ####
        mw = Gui.getMainWindow()
        styleCurrentTheme = getStyle()

        menu = QtGui.QMenu(mw)
        menu.setObjectName("styleQuickMenu")
        menu.setStyleSheet(styleCurrentTheme)

        actionContext = QtGui.QAction(menu)
        actionContext.setText(translate("QuickMenu", "Global context"))
        actionContext.setCheckable(True)
        actionContext.setChecked(config.get_params()["main"].GetBool("EnableContext"))
        actionContext.triggered.connect(lambda checked: onContext(checked))

        actionDisplaySpinBox = QtGui.QAction(menu)
        actionDisplaySpinBox.setText(translate("QuickMenu", "Direct SpinBox display"))
        actionDisplaySpinBox.setCheckable(True)
        actionDisplaySpinBox.setChecked(config.get_params()["main"].GetBool("DisplaySpinBox"))
        actionDisplaySpinBox.triggered.connect(lambda checked: onDisplaySpinBox(checked))

        menuPieMenu = QtGui.QMenu()
        menuPieMenu.setTitle(translate("QuickMenu", "PieMenu"))
        menuPieMenu.aboutToShow.connect(pieList)

        pieGroup = QtGui.QActionGroup(menu)
        pieGroup.setExclusive(True)
        pieGroup.triggered.connect(onPieGroup)

        menuToolBar = QtGui.QMenu()
        menuToolBar.setObjectName("styleQuickMenuItem")
        menuToolBar.setTitle(translate("QuickMenu", "ToolBar"))
        menuToolBar.setStyleSheet(styleCurrentTheme)
        menuToolBar.aboutToShow.connect(onMenuToolBar)

        toolbarGroup = QtGui.QMenu()
        toolbarGroupOps = QtGui.QActionGroup(toolbarGroup)
        toolbarGroupOps.setExclusive(True)
        toolbarGroup.triggered.connect(onToolbarGroup)

        prefAction = QtGui.QAction(menu)
        prefAction.setIconText(translate("QuickMenu", "Preferences"))

        prefButton = QtGui.QToolButton()
        prefButton.setDefaultAction(prefAction)
        prefButton.clicked.connect(onPrefButton)

        prefButtonWidgetAction = QtGui.QWidgetAction(menu)
        prefButtonWidgetAction.setDefaultWidget(prefButton)

        menu.addAction(actionContext)
        menu.addAction(actionDisplaySpinBox)
        menu.addSeparator()
        menu.addMenu(menuPieMenu)
        menu.addMenu(menuToolBar)
        menu.addSeparator()
        menu.addAction(prefButtonWidgetAction)

        icon = iconSize(buttonSize)
        radius = radiusSize(buttonSize)

        button = QtGui.QToolButton()
        button.setObjectName("styleButtonMenu")
        button.setMenu(menu)
        button.setProperty("ButtonX", 0)  # +, right
        button.setProperty("ButtonY", 32)  # +, down
        button.setGeometry(0, 0, buttonSize, buttonSize)
        button.setIconSize(QtCore.QSize(icon, icon))
        button.setStyleSheet(styleCurrentTheme + radius)
        button.setPopupMode(QtGui.QToolButton.ToolButtonPopupMode.InstantPopup)
        return button
    ### END QuickMenu   Def ###


    #### END Functions Def ####

    #### Main code ####

    #### Designer forms and runtime bindings ####
    global pieMenuDialog
    settings_form = load_form("PieMenuPreferences.ui", Gui.getMainWindow(),
                              (PieMenuDialog, CustomLineEdit), translate)
    pieMenuDialog = settings_form.root
    icons_form = load_form("IconPicker.ui", pieMenuDialog, translate=translate)
    window_icons = icons_form.root
    tabs = settings_form.tabs
    grid_widget = icons_form.grid_widget
    scroll_area = icons_form.scroll_area
    buttonBrowse = icons_form.buttonBrowse
    cancel_window_icons_button = icons_form.cancel_window_icons_button
    buttonIconPieMenu = settings_form.buttonIconPieMenu
    cBox = settings_form.cBox
    buttonAddPieMenu = settings_form.buttonAddPieMenu
    buttonRemovePieMenu = settings_form.buttonRemovePieMenu
    buttonRenamePieMenu = settings_form.buttonRenamePieMenu
    buttonCopyPieMenu = settings_form.buttonCopyPieMenu
    buttonExistingToolBar = settings_form.buttonExistingToolBar
    piemenuBoxGroup = settings_form.piemenuBoxGroup
    pieMenuTab = settings_form.pieMenuTab
    checkboxDefaultPie = settings_form.checkboxDefaultPie
    labelDefaultPie = settings_form.labelDefaultPie
    labelWbForPieMenu = settings_form.labelWbForPieMenu
    comboWbForPieMenu = settings_form.comboWbForPieMenu
    piemenuSettingGroup = settings_form.piemenuSettingGroup
    labelShape = settings_form.labelShape
    comboShape = settings_form.comboShape
    labelRadius = settings_form.labelRadius
    spinRadius = settings_form.spinRadius
    labelButton = settings_form.labelButton
    spinButton = settings_form.spinButton
    labelIconSpacing = settings_form.labelIconSpacing
    spinIconSpacing = settings_form.spinIconSpacing
    labelNumColumn = settings_form.labelNumColumn
    spinNumColumn = settings_form.spinNumColumn
    labelCommandPerCircle = settings_form.labelCommandPerCircle
    spinCommandPerCircle = settings_form.spinCommandPerCircle
    checkboxDisplayCommandName = settings_form.checkboxDisplayCommandName
    labeldisplayCommandName = settings_form.labeldisplayCommandName
    checkboxDisplayPreselect = settings_form.checkboxDisplayPreselect
    labelDisplayPreselect = settings_form.labelDisplayPreselect
    shapeGroup = settings_form.shapeGroup
    iconSpacingGroup = settings_form.iconSpacingGroup
    radioInnerPacked = settings_form.radioInnerPacked
    radioInnerEquallySpaced = settings_form.radioInnerEquallySpaced
    radioOuterPacked = settings_form.radioOuterPacked
    radioOuterEquallySpaced = settings_form.radioOuterEquallySpaced
    radioButtonPress = settings_form.radioButtonPress
    radioButtonHover = settings_form.radioButtonHover
    labelHoverDelay = settings_form.labelHoverDelay
    spinHoverDelay = settings_form.spinHoverDelay
    triggerModeGroup = settings_form.triggerModeGroup
    toolShortcutGroup = settings_form.toolShortcutGroup
    checkboxDisplayShortcut = settings_form.checkboxDisplayShortcut
    labelDisplayShortcut = settings_form.labelDisplayShortcut
    labelShortcutSize = settings_form.labelShortcutSize
    spinShortcutLabelSize = settings_form.spinShortcutLabelSize
    buttonListWidget = settings_form.buttonListWidget
    labelShortcut = settings_form.labelShortcut
    shortcutLineEdit = settings_form.shortcutLineEdit
    assignShortcutButton = settings_form.assignShortcutButton
    deleteShortcutButton = settings_form.deleteShortcutButton
    infoShortcut = settings_form.infoShortcut
    searchLineEdit = settings_form.searchLineEdit
    clearButton = settings_form.clearButton
    toolListWidget = settings_form.toolListWidget
    widgetContainer = settings_form.widgetContainer
    contextTab = settings_form.contextTab
    labelContextTable = settings_form.labelContextTable
    contextTable = settings_form.contextTable
    resetContextButton = settings_form.resetContextButton
    addContextConditions = settings_form.addContextConditions
    checkboxTriggerContext = settings_form.checkboxTriggerContext
    labelTriggerContext = settings_form.labelTriggerContext
    settingContextGroup = settings_form.settingContextGroup
    labelContextWorkbench = settings_form.labelContextWorkbench
    comboContextWorkbench = settings_form.comboContextWorkbench
    listContextConditions = settings_form.listContextConditions
    labelListContext = settings_form.labelListContext
    buttonBackToSettings = settings_form.buttonBackToSettings
    listToolBar = settings_form.listToolBar
    labelAddToolBar = settings_form.labelAddToolBar
    buttonAddToolBar = settings_form.buttonAddToolBar
    addToolBarGroup = settings_form.addToolBarGroup
    toolBarTab = settings_form.toolBarTab
    settingsTab = settings_form.settingsTab
    buttonAddSeparator = settings_form.buttonAddSeparator
    buttonAddShortcut = settings_form.buttonAddShortcut
    buttonRemoveCommand = settings_form.buttonRemoveCommand
    buttonUp = settings_form.buttonUp
    buttonDown = settings_form.buttonDown
    pieButtons = settings_form.pieButtons
    showPreviewWidget = settings_form.showPreviewWidget
    showPiemenu = settings_form.showPiemenu
    vSplitter = settings_form.vSplitter
    info_button = settings_form.info_button
    doc_button = settings_form.doc_button
    close_button = settings_form.close_button
    labelTheme = settings_form.labelTheme
    comboBoxTheme = settings_form.comboBoxTheme
    checkboxQuickMenu = settings_form.checkboxQuickMenu
    labelShowQuickMenu = settings_form.labelShowQuickMenu
    checkboxGlobalContext = settings_form.checkboxGlobalContext
    labelGlobalContext = settings_form.labelGlobalContext
    checkboxGlobalKeyToggle = settings_form.checkboxGlobalKeyToggle
    labelGlobalKeyToggle = settings_form.labelGlobalKeyToggle
    checkboxRightClick = settings_form.checkboxRightClick
    labelDelayRightClick = settings_form.labelDelayRightClick
    spinDelayRightClick = settings_form.spinDelayRightClick
    labelRightClick = settings_form.labelRightClick
    checkboxDisplaySpinBox = settings_form.checkboxDisplaySpinBox
    labelSpinBox = settings_form.labelSpinBox
    globalSettingsGroup = settings_form.globalSettingsGroup
    experimentalGroup = settings_form.experimentalGroup
    buttonParamExport = settings_form.buttonParamExport
    buttonParamImport = settings_form.buttonParamImport
    labelParamExport = settings_form.labelParamExport
    labelParamImport = settings_form.labelParamImport
    exportGroup = settings_form.exportGroup
    labelGlobalShortcut = settings_form.labelGlobalShortcut
    globalShortcutLineEdit = settings_form.globalShortcutLineEdit
    assignGlobalShortcutButton = settings_form.assignGlobalShortcutButton
    deleteGlobalShortcutButton = settings_form.deleteGlobalShortcutButton
    grid_layout = icons_form.grid_layout
    buttonsLayout = settings_form.buttonsLayout

    # Initialize parameter-backed values before connecting signals.
    radioGroup = QtGui.QButtonGroup(pieMenuDialog)
    radioGroup.addButton(radioButtonPress)
    radioGroup.addButton(radioButtonHover)

    ### group Tools Shortcuts ####

    enableShortcut = getParameterGroup(
        cBox.currentText(), "Bool", "EnableShorcut")
    if enableShortcut == "":
        enableShortcut = False

    toolShortcutGroup.setChecked(enableShortcut)

    #### group Individual Shortcut ####
    shortcutKey = getParameterGroup(
        cBox.currentText(), "String", "ShortcutKey")

    labelShortcut.setText(
        translate("PieMenuTab", "Current shortcut: ") + shortcutKey)

    shortcutLineEdit.setText(shortcutKey)

    #### Tool list container ####

    toolListWidget.sortItems(2, QtCore.Qt.AscendingOrder)
    toolListWidget.verticalHeader().setVisible(False)

    toolListWidget.horizontalHeader().setSortIndicatorShown(True)
    toolListWidget.horizontalHeader().setSortIndicator(2, QtCore.Qt.AscendingOrder)
    toolListWidget.horizontalHeader().setSectionsClickable(True)
    toolListWidget.horizontalHeader().setSectionsMovable(False)

    #### Tab ContextTab ####

    vertexItem = QtGui.QTableWidgetItem()
    vertexItem.setText(translate("ContextTab", "Vertex"))
    vertexItem.setToolTip(
        translate("ContextTab", "A vertex can be a point on a 2D or 3D object, a projected point, a point of origin, DatumPoint etc."))
    vertexItem.setFlags(QtCore.Qt.ItemIsEnabled)

    edgeItem = QtGui.QTableWidgetItem()
    edgeItem.setText(translate("ContextTab", "Edge"))
    edgeItem.setToolTip(
        translate("ContextTab", "An edge can be an line, circle, etc. spline on a 2D or 3D object."))
    edgeItem.setFlags(QtCore.Qt.ItemIsEnabled)

    faceItem = QtGui.QTableWidgetItem()
    faceItem.setText(translate("ContextTab", "Face"))
    faceItem.setToolTip(
        translate("ContextTab", "A face can be a face, a curve etc. of a 2D or 3D object."))
    faceItem.setFlags(QtCore.Qt.ItemIsEnabled)

    objectItem = QtGui.QTableWidgetItem()
    objectItem.setText(translate("ContextTab", "Object"))
    objectItem.setToolTip(
        translate("ContextTab", "An object can be any element contained in the construction tree: body, part, feature, etc."))
    objectItem.setFlags(QtCore.Qt.ItemIsEnabled)
    
    axisItem = QtGui.QTableWidgetItem()
    axisItem.setText(translate("ContextTab", "Axis"))
    axisItem.setToolTip(
        translate("ContextTab", "An axis can be X, Y, Z axis, H or V axis in Sketcher or DatumLine"))
    axisItem.setFlags(QtCore.Qt.ItemIsEnabled)
    
    planeItem = QtGui.QTableWidgetItem()
    planeItem.setText(translate("ContextTab", "Plane"))
    planeItem.setToolTip(
        translate("ContextTab", "An plane can be XY, XZ or YZ plane or DatumPlane"))
    planeItem.setFlags(QtCore.Qt.ItemIsEnabled)

    vertexComboBox = comboBox("VertexSign")
    edgeComboBox = comboBox("EdgeSign")
    faceComboBox = comboBox("FaceSign")
    objectComboBox = comboBox("ObjectSign")
    axisComboBox = comboBox("AxisSign")
    planeComboBox = comboBox("PlaneSign")

    vertexSpin = spinBox("VertexValue")
    edgeSpin = spinBox("EdgeValue")
    faceSpin = spinBox("FaceValue")
    objectSpin = spinBox("ObjectValue")
    axisSpin = spinBox("AxisValue")
    planeSpin = spinBox("PlaneValue")

    # contextTable.setMaximumHeight(160)
    # contextTable.setFrameStyle(QtGui.QFrame.NoFrame)
    contextTable.verticalHeader().setVisible(False)
    contextTable.horizontalHeader().setVisible(False)

    contextTable.setItem(0, 0, vertexItem)
    contextTable.setCellWidget(0, 1, vertexComboBox)
    contextTable.setCellWidget(0, 2, vertexSpin)

    contextTable.setItem(1, 0, edgeItem)
    contextTable.setCellWidget(1, 1, edgeComboBox)
    contextTable.setCellWidget(1, 2, edgeSpin)

    contextTable.setItem(2, 0, faceItem)
    contextTable.setCellWidget(2, 1, faceComboBox)
    contextTable.setCellWidget(2, 2, faceSpin)

    contextTable.setItem(3, 0, objectItem)
    contextTable.setCellWidget(3, 1, objectComboBox)
    contextTable.setCellWidget(3, 2, objectSpin)
    
    contextTable.setItem(4, 0, axisItem)
    contextTable.setCellWidget(4, 1, axisComboBox)
    contextTable.setCellWidget(4, 2, axisSpin)

    contextTable.setItem(5, 0, planeItem)
    contextTable.setCellWidget(5, 1, planeComboBox)
    contextTable.setCellWidget(5, 2, planeSpin)

    listContextConditions.verticalHeader().setVisible(False)

    listContextConditions.horizontalHeader().setSectionsClickable(True)
    listContextConditions.horizontalHeader().setSectionsMovable(False)
    listContextConditions.horizontalHeader().setVisible(False)

    listContextConditions.setSizePolicy(
        QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Maximum)

    #### Tab ToolBar ####

    listToolBar.sortItems(QtCore.Qt.AscendingOrder)

    #### Tab Global Settings ####

    #### buttons actions list ####

    buttonListWidget.verticalHeader().setVisible(False)
    buttonListWidget.horizontalHeaderItem(0).setTextAlignment(
        QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
    buttonListWidget.horizontalHeaderItem(1).setTextAlignment(
        QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
    buttonListWidget.horizontalHeader().setMinimumSectionSize(60)

    showPreviewWidget.verticalHeader().setVisible(False)
    showPreviewWidget.horizontalHeader().setMinimumSectionSize(100)

    #### Main Layout####

    #### Global Settings ####

    getTheme()

    checkboxQuickMenu.setChecked(config.get_params()["main"].GetBool("ShowQuickMenu"))

    enableContext = config.get_params()["main"].GetBool("EnableContext")
    checkboxGlobalContext.setChecked(enableContext)

    checkboxGlobalKeyToggle.setChecked(
        getParameterGlobal("Bool", "GlobalKeyToggle"))

    checkboxRightClick.setChecked(
        getParameterGlobal("Bool", "RightClickTrigger"))

    spinDelayRightClick.setValue(getParameterGlobal("Int", "DelayRightClick"))

    checkboxDisplaySpinBox.setChecked(config.get_params()["main"].GetBool("DisplaySpinBox"))

    # spinBoxGroup = QGroupBox(translate("GlobalSettingsTab", "SpinBox settings"))
    # spinBoxGroup.setLayout(QtGui.QVBoxLayout())
    # spinBoxGroup.layout().addLayout(layoutSpinBox)

    state.app_state.global_shortcut_key = config.get_params()["main"].GetString("GlobalShortcutKey")

    globalShortcutLineEdit.setText(state.app_state.global_shortcut_key)

    # settingsTabLayout.insertWidget(1, spinBoxGroup)


    # Connect after configuration so loading form defaults cannot trigger handlers.
    buttonBrowse.clicked.connect(onButtonBrowseIcon)
    cancel_window_icons_button.clicked.connect(window_icons_close)
    buttonIconPieMenu.clicked.connect(onButtonIconPieMenu)
    cBox.currentIndexChanged.connect(onPieChange)
    buttonAddPieMenu.clicked.connect(onButtonAddPieMenu)
    buttonRemovePieMenu.clicked.connect(onButtonRemovePieMenu)
    buttonRenamePieMenu.clicked.connect(onButtonRenamePieMenu)
    buttonCopyPieMenu.clicked.connect(onButtonCopyPieMenu)
    buttonExistingToolBar.clicked.connect(onButtonToolBar)
    checkboxDefaultPie.stateChanged.connect(lambda state: onDefaultPie(state))
    comboWbForPieMenu.currentIndexChanged.connect(onWbForPieMenu)
    comboShape.currentIndexChanged.connect(setShape)
    spinRadius.valueChanged.connect(onSpinRadius)
    spinButton.valueChanged.connect(onSpinButton)
    spinIconSpacing.valueChanged.connect(onIconSpacing)
    spinNumColumn.valueChanged.connect(onNumColumn)
    spinCommandPerCircle.valueChanged.connect(onCommandPerCircle)
    checkboxDisplayCommandName.stateChanged.connect(
        lambda state: onDisplayCommandName(state))
    checkboxDisplayPreselect.stateChanged.connect(
        lambda state: onDisplayPreselect(state))
    radioInnerPacked.toggled.connect(
        lambda checked: onRingIconSpacing("PackInnerIcons", checked))
    radioOuterPacked.toggled.connect(
        lambda checked: onRingIconSpacing("PackOuterIcons", checked))
    radioButtonPress.toggled.connect(
        lambda checked, data="Press": setTriggerMode(data))
    radioButtonHover.toggled.connect(
        lambda checked, data="Hover":  setTriggerMode(data))
    spinHoverDelay.valueChanged.connect(onSpinHoverDelay)
    toolShortcutGroup.toggled.connect(lambda state: onEnableShortcut(state))
    checkboxDisplayShortcut.stateChanged.connect(
        lambda state: onDisplayShortcut(state))
    spinShortcutLabelSize.valueChanged.connect(onSpinShortcutLabelSize)
    assignShortcutButton.clicked.connect(
        lambda: updateShortcutKey(shortcutLineEdit.text()))
    deleteShortcutButton.clicked.connect(lambda: updateShortcutKey(""))
    searchLineEdit.textChanged.connect(searchInToolList)
    clearButton.clicked.connect(searchLineEdit.clear)
    toolListWidget.horizontalHeader().sectionClicked.connect(sortToolListByColumn)
    toolListWidget.itemChanged.connect(onToolListWidget)
    resetContextButton.clicked.connect(onResetContextTable)
    addContextConditions.clicked.connect(onAddContextConditions)
    checkboxTriggerContext.stateChanged.connect(
        lambda state: onTriggerContext(state))
    comboContextWorkbench.currentIndexChanged.connect(setContextWorkbench)
    listContextConditions.itemSelectionChanged.connect(onRowSelected)
    buttonBackToSettings.clicked.connect(onBackToSettings)
    listToolBar.itemSelectionChanged.connect(showListToolBar)
    buttonAddToolBar.clicked.connect(onAddToolBar)
    buttonAddSeparator.clicked.connect(onButtonAddSeparator)
    buttonAddShortcut.clicked.connect(onButtonAddShortcut)
    buttonRemoveCommand.clicked.connect(onButtonRemoveCommand)
    buttonUp.clicked.connect(onButtonUp)
    buttonDown.clicked.connect(onButtonDown)
    info_button.clicked.connect(infoPopup)
    doc_button.clicked.connect(documentationLink)
    close_button.clicked.connect(pieMenuDialog.close)
    comboBoxTheme.currentIndexChanged.connect(setTheme)
    checkboxQuickMenu.stateChanged.connect(
        lambda state: onShowQuickMenu(state))
    checkboxGlobalContext.stateChanged.connect(lambda state: onContext(state))
    checkboxGlobalKeyToggle.stateChanged.connect(setGlobalKeyToggle)
    checkboxRightClick.stateChanged.connect(
        lambda state: onRightClickTrigger(state))
    spinDelayRightClick.valueChanged.connect(onSpinDelayRightClick)
    checkboxDisplaySpinBox.stateChanged.connect(
        lambda state: onDisplaySpinBox(state))
    buttonParamExport.clicked.connect(onParamExport)
    buttonParamImport.clicked.connect(onParamImport)
    assignGlobalShortcutButton.clicked.connect(
        lambda: updateGlobalShortcutKey(globalShortcutLineEdit.text()))
    deleteGlobalShortcutButton.clicked.connect(
        lambda: updateGlobalShortcutKey(""))
    # Create a fake command in FreeCAD to handle the PieMenu Separator
    Gui.addCommand('PieMenu_Separator', PieMenuSeparator())
    # createNestedPieMenus()

    mw = Gui.getMainWindow()

    # the separator command and the stored shortcut entries need plain actions
    # because FreeCAD only materialises command actions through menus/toolbars
    registerSeparatorAction()
    registerShortcutEntryActions()

    start = True
    for action in mw.findChildren(QtGui.QAction):
        if action.objectName() == "PieMenuShortCut":
            start = False
        else:
            pass

    if start:
        compositingManager = True
        if QtCore.qVersion() < "5":
            windowShadow = False
        else:
            windowShadow = True
        if platform.system() == "Linux":
            try:
                if QtGui.QX11Info.isCompositingManagerRunning():
                    windowShadow = True
                else:
                    compositingManager = False
            except AttributeError:
                windowShadow = True
        else:
            pass
        if platform.system() == "Windows":
            windowShadow = True
        else:
            pass

        contextList()
        selObserver = SelObserver()
        addObserver()
        setContextConditions()
        PieMenuInstance = PieMenu()
        actionKey = QtGui.QAction(mw)
        actionKey.setText("Invoke pie menu")
        actionKey.setObjectName("PieMenuShortCut")
        # fix shortcut not trigger on fresh install
        state.app_state.global_shortcut_key = config.get_params()["main"].GetString("GlobalShortcutKey")

        actionKey.setShortcut(QtGui.QKeySequence(state.app_state.global_shortcut_key))
        actionKey.triggered.connect(PieMenuInstance.showAtMouseInstance)
        mw.addAction(actionKey)

        getShortcutList()
        legacyFix()
        # Fix errors at first init
        getGroup()
        # let the addition of the Edit menu entry wait until FC is ready for it
        t = QtCore.QTimer()
        t.timeout.connect(addEditMenuEntry)
        t.start(500)

    else:
        pass


pieMenuStart()
