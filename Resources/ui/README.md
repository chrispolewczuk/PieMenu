# Qt Designer forms

Open these files directly in Qt Designer:

| Form | Interface |
| --- | --- |
| `PieMenuPreferences.ui` | Settings tabs, command selectors, toolbar browser, preview container, and footer |
| `IconPicker.ui` | Icon grid container and browse/cancel buttons |
| `ShortcutEditor.ui` | Add/edit shortcut dialog |

The forms load at runtime through `piemenu/forms.py`; no generated `ui_*.py` files or compilation step is needed.

Keep existing object names when editing a form. `InitGui.py` binds widgets and layouts by those names, then connects signals after initializing saved settings. Add new controls to the form and bind them explicitly in Python.

`CustomLineEdit` and `PieMenuDialog` are promoted widgets. Designer uses their base `QLineEdit` and `QDialog` appearance; the loader registers the Python subclasses from `InitGui.py` so keyboard handling and dialog close behavior remain active.

Static labels, tooltips, constraints, icons, layouts, and spacers belong in the forms. Values loaded from user parameters, populated tables, selection-condition editors, the icon grid contents, and the live pie preview remain in Python.

Existing translation catalogs use several contexts in one dialog. The `_translationContext_text`, `_translationContext_title`, `_translationContext_toolTip`, and related dynamic properties preserve those contexts. Text is marked `notr` to avoid an extra translation with the form's class name. Keep the context property with its label; update the matching `Resources/translation` catalogs when introducing or changing translatable source text.

Icon paths are relative to this directory. The loader sets its working directory accordingly, so forms work both in a checkout and in the installed FreeCAD add-on.

`tests/test_forms.py` loads the forms and checks custom widgets, table columns, defaults, visibility, icon paths, translations, and missing-file diagnostics. It runs with the other unit tests when a Qt application is available.
