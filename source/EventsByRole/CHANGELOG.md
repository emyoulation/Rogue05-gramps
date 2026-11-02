# Events by Role changelog
<!-- undocked=false -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

## 1.0.2
- Fixed: using the view could make Gramps discard all of its preferences. The view registered a mixed-case column-width key (`spacing.EventsByRole`) in gramps.ini; after a few sessions, gramps.ini held the key twice in different capitalizations, Gramps rejected the file as unreadable and recreated it with defaults. The key is now lowercase (`spacing.eventsbyrole`). To clean up an affected system, close Gramps and remove the `EventsByRole=` and `eventsbyrole=` lines from the `[spacing]` section of gramps.ini.
- Fixed: the view no longer crashes on Gramps 5.2 when showing the role columns (5.2 passes event rows as tuples, not as the objects used by Gramps 6.0 and newer).
- Fixed: column order, widths and hidden columns are now kept when the set of roles changes, for example after adding a custom role or opening another tree. Columns for roles that no longer exist are dropped and columns for new roles are added at the end. Previously the whole column layout was reset.
- Fixed: opening another tree now shows that tree's custom roles. Previously the role columns of the first tree stayed in place.
- Fixed: new role columns now appear as soon as a custom role is added. Previously the column headers could get out of step with the data shown under them.
- Fixed: a possible crash when building the columns, caused by column settings that were saved only partly (settings equal to their defaults are not written) and then read back out of step with each other.
- Added: a Help button on the toolbar. It shows this README in the Markdown Dash gramplet when that addon is installed and active, and otherwise opens the README on GitHub in the web browser (the new `help_url` in EventsByRole.gpr.py). The tooltip says which of the two a click will show. The button uses the color help icon of the current icon theme, or the copy in the addon `media` folder when the theme has none.
- Changed: the view settings are now kept in `EventsByRole.ini` in the addon folder instead of the main Gramps settings folder, with a `[meta]` section naming the addon (`plugin_id`) and the settings layout (`schema_version`). A settings file from another addon, from an older incompatible layout or from a newer release is ignored and replaced by the defaults. The old `Events_eventsbyrole.ini` in the main settings folder is no longer used and can be deleted.

## 1.0.1
- Added the author to the add-on registration (`authors` in EventsByRole.gpr.py), so the Addon Manager and Plugin Manager credit Wojciech Sopot.
- Added copyright notices for Wojciech Sopot (Rogue05) to the headers of EventsByRole.py and EventsByRole.gpr.py.

## 1.0.0
- First release by Wojciech Sopot (Rogue05) in [Rogue05/Gramps-filter](https://github.com/Rogue05/Gramps-filter/tree/main/source/EventsByRole): an alternate Events view with one participant column for each standard and custom event role, covering both people and families, for Gramps 5.2, 6.0 and 6.1.

## Outstanding issues
### Planned/NYI
- Sorting by a role column is slow on large trees, because it looks up the participants of every event and the row cache is smaller than the tree.

### Needs discussion
- Whether column settings in the old `Events_eventsbyrole.ini` should be carried over into the new `EventsByRole.ini`. They are currently ignored; the layout was reset on every role change before 1.0.2 anyway.

### Beyond scope
- The underlying gramps.ini bug is in Gramps core: `PersistentTreeView.set_config_name()` registers keys without lowercasing them, while `ConfigManager.load()` lowercases every key it reads. Any list view addon whose `get_config_name()` returns a mixed-case name is affected.
