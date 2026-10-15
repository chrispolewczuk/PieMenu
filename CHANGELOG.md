# CHANGELOG

## 1.14

- Remove duplicate entries from the stored menu list so each PieMenu appears only once in the settings dropdown.
- Fix division by zero for Concentric / Star shapes when "Command for first circle" is unset.
- Fix the existing-name check when creating or copying a PieMenu under Python 3.
- Shortcut entries are included in settings exports and imports through their global PieMenu parameters.
- Outer-ring placement adds a gap of 60% of the rendered icon size to the button width between rings.
- Size settings-panel table columns to their contents and stretch the final column to fill remaining list width, including after filtering and resizing.
- Parent the trigger-mode button group to the settings dialog so garbage collection cannot invalidate the Press / Hover radio buttons after startup. Clamp command-label fonts to at least one pixel so tightly spaced labels cannot generate a zero-pixel font.
- Move the preferences dialog, icon picker, and shortcut editor layouts into Qt Designer `.ui` forms under `Resources/ui`. Python retains signal handlers, saved settings, context-condition editors, and generated pie-menu buttons. The form loader registers custom shortcut fields and preserves existing translation contexts. See the [UI editing guide](Resources/ui/README.md) for layout changes and runtime bindings.
- Add an Icon Spacing section below Shape with independent Packed / Equally spaced radio buttons for the Inner Ring and Outer Ring. Both default to native equal spacing, with per-menu choices saved and inherited by new menus. Inner packing also works without an outer ring.
- Reuse the settings dialog and skip duplicate startup before rebuilding its UI, preventing the event filter from accessing deleted settings tabs. The dialog and filter now belong to the main window.
- Add mutually exclusive Inner / Outer checkbox columns to the Tools tab, saving ring assignments per menu. Pie menus display assigned outer commands in a second ring with a gap of 60% of the rendered icon size. Command names and preselect buttons are disabled for this layout; ring assignment replaces the outer-ring toggle and first-circle count input for Pie shapes.
- Add a built-in center settings button using the PieMenu logo: it replaces the close ring on menus other than View when no accept/cancel controls or feature inputs occupy the center. Clicking it closes the pie and opens settings with that menu selected. The View menu retains its existing center behavior and never shows the settings icon.
- Move the "PieMenu" entry from the "Accessories" menu to the bottom of the "Edit" menu, behind a separator: added the `PieMenu_Settings` FreeCAD command (`PieMenuSettingsCommand`, `MenuText` now simply "PieMenu", `Activated()` calls `onControl()`) and `PieMenuWorkbenchManipulator.modifyMenuBar()`, which returns `{"append": "Separator", "menuItem": "Std_DlgPreferences"}` followed by `{"append": "PieMenu_Settings", "menuItem": "Std_DlgPreferences"}`. `addEditMenuEntry()` (reached from the existing 500 ms `QTimer`) registers them with `Gui.addCommand()` and `Gui.addWorkbenchManipulator()` (guarded by `getattr(Gui, "PieMenuWorkbenchManipulator", None)`), then calls `Gui.activeWorkbench().reloadActive()` so the entry shows without restarting. Removed `addAccessoriesMenu()` / `accessoriesMenu()`; the `AccesoriesMenu` translation context is kept so existing translations still resolve.
- Remove the dedicated "View" pie shortcut hook: deleted `viewPieName` / `viewPieShortcut` / `defaultGlobalShortcut`, the start-up fallback that rewrote `GlobalShortcutKey` to `TAB` when it collided, the `PieMenuShortCutView` `QAction`, and the "Shortcut reserved for the View pie menu !" branch in `updateGlobalShortcutKey()`.
- Rework per-pie shortcut binding in `getShortcutList()`: each entry now carries the pie's `DefaultWorkbench`, shortcuts are grouped per key in configuration order, and exactly one `QShortcut` is created per key (several `QShortcut`s on the same sequence make Qt cycle between them, alternating which menu opens). The reserved set now holds only the global shortcut, empty keys are skipped, and when a key is shared by several pies that *all* declare a workbench association the handler dispatches on `Gui.activeWorkbench().name()` (like the global shortcut) instead of always taking the first pie. Deleted the unused Qt5 variant of `getShortcutList()`.
- New pies inherit the "PieMenu" tab settings of the previously created menu: added the `defaultPieTabKeys` tuple (`(name, type, fallback)`, now also covering `IconSpacing`, `DisplayCommand`, `DisplayShorcut` with a `None` fallback that leaves the key unset), `getLastCreatedTabSettings()` (reads `main/LastCreatedPie` via `GetContents()` / `GetInt()` / `GetString()` / `GetBool()`), and `setDefaultValues(group, sourceSettings=None)`. `createPie()` reads the source settings *before* registering the new index (so a recycled index is never mistaken for the source) and stores the new index in `main/LastCreatedPie`, skipped for `restore_default_pie`.
- Stop creating the hidden `PieMenuTB` toolbar: `onButtonAddSeparator()` no longer writes `Name = PieMenuTB` and `PieMenu_Separator = FreeCAD` into `User parameter:BaseApp/Workbench/Global/Toolbar/Custom_PieMenu` (the block is left commented as a reference) and an existing `PieMenuTB` is untouched (it stays hidden). The workbench reload is gone too, because the separator command is now backed by a plain action (see below).
- Fix the "Add separator" button: FreeCAD only materialises a command's `QAction` once the command is added to a menu or a toolbar, so dropping the hidden `PieMenuTB` toolbar left `PieMenu_Separator` without an action and `getGuiActionMapAll()` (which keys actions by `objectName()`) could no longer resolve the stored ids. `registerSeparatorAction()`, called once from `pieMenuStart()`, now creates a plain `QAction` on the main window (`objectName` `PieMenu_Separator`, text `translate('PieMenuTab', 'Separator')`, `resources.iconAddSeparator`, disabled like the command's `IsActive()`); an action still created by a leftover `PieMenuTB` toolbar is found with `findChild()` and reused. `onButtonAddSeparator()` only hides a leftover `PieMenuTB` and appends the id through the new `appendCommandToPieList()` helper, and the unused local code that shadowed `toolList` was removed.
- New "Add shortcut" pie entry (button between "Add separator" and "Remove selected command"): a shortcut entry is a pie button that replays a keyboard shortcut. Entries are stored globally under `User parameter:BaseApp/PieMenu/Shortcuts` (`NextId`, `EntryList` holding the ".,."-joined entry numbers as the source of truth, and an `Entry_<n>` group with `Name` / `Icon` / `Key`) and registered at start-up by `registerShortcutEntryActions()` as plain `QAction`s (`objectName` `PieMenu_ShortcutEntry_<n>`, non-null icon required because `getGuiActionMapAll()` drops actions without one) so the existing pie resolution needs no change. `onButtonAddShortcut()` opens `showShortcutEntryDialog()` (name, icon and key sequence; Validate rejects an empty or invalid sequence and the shared conflict warning is shown inside the dialog), which in create mode also appends the id to the current pie's `ToolList`; the entry selected in the action list can be edited in place. Triggering goes through `triggerShortcutEntry()` → `runShortcutSequence()`: an enabled `QAction` bound to the same key wins, otherwise `sendKeySequenceEvents()` replays the sequence chord by chord (50 ms apart) on the focused widget, handling both Qt5 (`int` key combination) and Qt6 (`QKeyCombination`). Shortcut entries display their key in the action list's "Shortcut" column (`buttonList()`) while still consuming a tool-shortcut letter, `getShortcutEntryKey()` / `formatKeySequence()` provide the text, and `getAssignedShortcut()` reports the stored keys so `compareAndDisplayWarning()` flags collisions. The icon picker is reused through the shared `iconPickerTarget` state, which also fixes the duplicated icon buttons when the picker is reopened.
- Bump the version to 1.14 (`PIE_MENU_VERSION` in `InitGui.py`, `package.xml` `1.14` / `2026-10-15` date field).

## 1.13
- Refactor monolithic code https://github.com/Grubuntu/PieMenu/pull/137 (Ben-PH)

## 1.12.4
- Fix https://github.com/Grubuntu/PieMenu/issues/138
## 1.12.3
- Fix SideType/MidPlane parameter depending FreeCAD version

## 1.12.2
- Fix 'Midplane' property being set for the extrusion of Sketch is deprecated and has been replaced by the 'SideType' property in FeatureExtrude.

## 1.12.1
Fix https://github.com/Grubuntu/PieMenu/issues/130

## 1.12
- Add setting to show directly Quick Spinbox or not https://github.com/Grubuntu/PieMenu/issues/126
- Increase spinbox size a little bit
- Pre fix qt6 issues in context tab https://github.com/Grubuntu/PieMenu/issues/125
- Fix issues with Freecad version 1.1.0 (41789) : PieMenus didn't work : Rewrite self.menu : QMenu > QWidget to complie with Qt6
- Remove some redondant code

## 1.11.3
- Fix useless code
- Fix https://github.com/Grubuntu/PieMenu/issues/124
- Code factorization

## 1.11.2
- Fix issue in remove pie function
- Fix issue with plane, axis and datum in context mode
  
## 1.11.1
- Remove : take account of original axes and planes in the context in order to solve an issue
  
## 1.11
- Add ability to add up to 4 rules in context tab
- Added to take account of X,Y and Z Axis (Edge in Context), XY, XZ and YZ Plane (Face in Context) in Context selection.

## 1.10.2
- Fix context not work with external geometry : https://github.com/Grubuntu/PieMenu/issues/116

## 1.10.1
- Fix user config path and export settings extension (hasecilu)
- Fix format for translation (hasecilu)

### 1.10
- Added workbench in toollist 
- Added ability to sort column tool and workbench column ascending or descending
- Added ability to search WB in searchtool
- Added fix for replace "Std_PieMenu_" by "PieMenu_" to comply with standard WB naming 
- Factorize some code
- Removal of the ‘PieMenu’ header from the name of nested menus https://github.com/Grubuntu/PieMenu/issues/112

### 1.9.5
- Fix https://github.com/Grubuntu/PieMenu/issues/109 : circular central button was not circular with the Opentheme theme
  
### 1.9.4
- Fix [#106] : FreeCAD crash when we quit Sketcher with PieMenu validation button and 'Sketcher_Dimension'/'Sketcher_CompDimensionTools' is active
Added ability to move or delete severals command at the same time in list tools : [#105](https://github.com/Grubuntu/PieMenu/issues/105)

### 1.9.3
- Fix copy PieMenu not duplicate all parameters https://github.com/Grubuntu/PieMenu/issues/104
- Partially fix (https://github.com/Grubuntu/PieMenu/issues/106)

### 1.9.2
- Qt6 fix : pressing the global shortcut no longer opens PieMenu
- Qt6 fix : modifiers shortcut were broken
- Qt6 fix : keyValue == False in updateCommands()
 -Qt6 fix : function onToolListWidget() were broken, setting showquickmenu were broken
- Qt6 fix : workbenches toolbars were broken
- Qt6 fix : context mode and setting globalcontext were instable
- Qt6 fix : add eventfilter to catch "minimize event", remove WA_MacAlwaysShowToolWindow : not supported in the same way in Qt5
- Fix : setting immediate trigger
- Fix :problem in createpie (add onpiechange()) to update values after create a new PieMenu

### 1.9.1
- Fix window_icon that appears under the dialog window on Linux system

### 1.9
- Added the ability to use FreeCAD's built-in icons for PieMenus (https://github.com/Grubuntu/PieMenu/issues/97)

### 1.8.1
- Use join() method from path module (as WIP-UIFile)
- Fix issue : https://github.com/Grubuntu/PieMenu/issues/94
- Fix some useless code

### 1.8
- Added import/export PieMenu settings
- Clean some code
  
### 1.7.6
- Fix issue : PieMenu crash at launch with Freecad 0.22 Version above 38001 (https://github.com/Grubuntu/PieMenu/issues/89)
  
### 1.7.5
- Fix issue : when left click in PiemenuDialog, it hid the preview

### 1.7.4
- Fix error message on hover in preview toolbartab
- Fix flickering when multi selections (CTRL) on context mode
- Fix submenus in sketcher edit mode : https://github.com/Grubuntu/PieMenu/issues/87

### 1.7.3
Fix issue with the preselection buttons on hover

### 1.7.2
Fix issue with the  display of the preselection button

### 1.7.1
Fix issue https://github.com/Grubuntu/PieMenu/issues/83 and some warnings about 'font size < 0'

### 1.7

- Added Piemenu preview in Preferences
- Move cBox to the up of settings, disable it when toolBarTab is active
- Fix cBox order
- Added Preselect arrow feature
- Added ability to set a WB for Context mode
- Added added management of the CTRL key for multiple selection in Context mode
- Remove button size limitation and set mini and maxi button size (16-120)
- Remove PiemenuDialog fixed size, position and set it modal.
- Fix cBox index to CurrentPie when the Preferences settings are opened
- Fix icon definition for default PieMenu
- Introduction of context immediate trigger with setting in contextTab

### 1.6

- Added ability to add a custom icon for each PieMenu (SVG or ICO)
- Added ability to call a PieMenu in an other PieMenu (nested PieMenu)
- Added new Toolbars tab in Preferences setting for adding existing FreeCAD's toolbar as new PieMenu
- Added experimental feature : long right click can open the current PieMenu
- Added offset of 1/2 icon for outer rings for Concentric shape
- Fix pyside inconsistent imports

### 1.5.1
- Fix problem : the workbenches were no longer available in the PieMenus due to FreeCAD 0.22Dev code changes
  
### 1.5
- Added expressions in fast spinbox
- Added DEL, SUPPR, UP and DOWN key for delete and move Tools il toollist (Settins > Tools tab)
- Added documentation link to wiki
- Added Icon PieMenu to Preference dialog window
- Added toogle behavior for individuals shortcuts (Limitation : works only for -ONE KEY- shortcuts or -'Modifier' + KEY- shortcuts (not for multikeysequence shortcuts eg. -V,G-)
- Added tools shortcuts keys ('0 to 9' and 'A to Z', except 'X' which bug), update stylesheet according to this new feature
- Enable the tools shortcuts will add a column with shortcuts in toollist
- Added show/hide tools's shortcuts : + spinbox for selected font size
- Added buttons to clear shortcut and globalshortcut
- Added checkbox to set the defaut PieMenu in Preferences
- Highlighting the default PieMenubox by an arrow in front in PieMenu's list and in QuickMenu
- Added validation with 'Enter' and 'Return' keys, when buttons "Validate" and "Cancel" are visible.(as a side-effect, pressing the Enter and return keys also hides the PieMenu)
- Matches the style of the Preferences window with the style of FreeCAD Preferences: Groupboxes, Checkboxes left aligned, Spinbox stretched etc
- Rearranging code

### 1.4.2
- Fix problem: when adding WB that doesn't exist in other FreeCAD version, example: AssemblyWB exists in 0.22 but not in 0.21.
  
### 1.4.1
- Fix bug with workbench associated

### 1.4
- Added workbench associated setting
- Added triggermode setting for each PieMenu
- Added global shortcut toggle mode setting
- Clean some code
- Fix vertical alignment for labels in Preferences
- Added ability to add separators in PieMenu
- Added save settings to disk when you close the preferences window
- Update script for update translation
- Added Polish translation

### 1.3.9
- Fix spacing with command names for Pie shape
- Fix style for command name LeftRight shape
- Added shapes:"Concentric" and "Star"
- Added ability to open PieMenu without file opened

### 1.3.8.2
- Added support for theme accent color (FreeCad>Preferences>Display>Theme>Accent Color)
- Fix default stylesheet to Legacy.qss if no existing stylesheet is set
- Added stylesheet Accents.qss

### 1.3.8.1
- Fix issue with stylesheet

### 1.3.8
- Added a checkbox in fast spinbox mode for Pocket/Pad : Through all, Symmetric, Reversed
- Changing spinbox type to accept calculations and added units
- Reactivation of the quickmenu in the sketcher, the problem seems resolved (def getGroup())
- Fix some bugs : problem when create a ToolBar via QuickMenu, problem with command name setting...
- Remove some useless/duplicate code (def actualizeWorkbenchActions)  
- Rearrangement of menu priorities for Global shortcut: Sketcher, Context, ToolBar, Current Pie (def updateCommands)
- Added command name for LeftRight shape (Pgilfernandez)
- Added French Support

### 1.3.7
- Add translation support, Spanish translation, Small cleanup.(hasecilu) 
- Add Icon spacing, stylabe QuickMenu and many cosmetics improvements (Pgilfernandez)
- Add new shape Left and Right (Pgilfernandez)
- Fix random bug with eventfilter

### 1.3.6
- Update layout of PieMenu Preferences for better readability (Pgilfernandez)
- Fix some typos (Pgilfernandez)
- Added some styles for QLabel command name (Pgilfernandez)
- Added "LeftRight" shape
- Fix problem with ghosting when reload workbenches

### 1.3.5
- Factorization and clean some code
- Added differents shapes for PieMenus
- Added possibility to display the command name in the menu (only Pie shape)
- Added a button with information about developers and licence (Pgilfernandez)
  
### 1.3.4
- Move globals settings on a new tab
- Added setting for show or not the QuickMenu
- Added checkbox in parameters for Contextual activation
- Set default theme (Legacy) on a new installation
- Update stylesheets for #styleButtonMenu::menu-indicator (setting for QuickMenu)

## Manual installation reference

FreeCAD's module installation path depends on the operating system and profile. To locate the user's application data directory, enter this command in FreeCAD's Python console:

```python
App.getUserAppDataDir()
```

Place the PieMenu folder inside the `Mod` directory. Example paths to its startup file:

| Platform | Example path |
| --- | --- |
| Linux | `/home/user/.local/share/FreeCAD/Mod/PieMenu/InitGui.py` |
| macOS | `/Users/user_name/Library/Preferences/FreeCAD/Mod/PieMenu/InitGui.py` |
| Windows | `C:\Users\user_name\AppData\Roaming\FreeCAD\Mod\PieMenu\InitGui.py` |
