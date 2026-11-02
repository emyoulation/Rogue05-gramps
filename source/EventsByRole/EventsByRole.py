#
# Gramps - a GTK+/GNOME based genealogy program
# Copyright 2026     Wojciech Sopot (Rogue05)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#

"""An Events-category view that separates participants into role columns."""

import logging
import os
import shutil
from urllib.parse import quote
from xml.sax.saxutils import escape

from gi.repository import Gio, GLib, Gtk

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.config import config
from gramps.gen.lib import EventRoleType
from gramps.gen.plug import PluginRegister
from gramps.gen.utils.db import family_name
from gramps.gen.utils.lru import LRU
from gramps.gui.dialog import OkDialog
from gramps.gui.pluginmanager import GuiPluginManager
from gramps.gui.views.listview import ListView, TEXT
from gramps.gui.views.treemodels.eventmodel import EventModel
from gramps.gui.views.treemodels.flatbasemodel import FlatBaseModel
from gramps.plugins.view.eventview import (
    EventBookmarks,
    EventSidebarFilter,
    EventView,
)

_ = glocale.translation.sgettext

LOG = logging.getLogger(__name__)

PLUGIN_ID = "eventsbyrole"  # matches id= in the .gpr.py
INI_SCHEMA_VERSION = 1  # layout this code writes
INI_MIN_COMPATIBLE = 1  # oldest layout this code can still read

BASE_COLUMN_COUNT = 8  # Description .. Last Changed, before the role columns
BASE_COLUMN_SIZES = [150, 80, 110, 140, 150, 35, 140, 120]
ROLE_COLUMN_SIZE = 160


def _as_int(value):
    """Return value as an int, or None if it is blank or not a number."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_role_columns(db):
    """Return every standard and tree-specific custom role, in stable order."""
    roles = []
    seen = set()

    for value in sorted(EventRoleType._I2EMAP):
        if value == EventRoleType._CUSTOM:
            continue
        role = EventRoleType(value)
        role_key = role.xml_str()
        if role_key and role_key not in seen:
            roles.append((role_key, str(role)))
            seen.add(role_key)

    try:
        custom_roles = db.get_event_roles()
    except AttributeError:
        custom_roles = []

    for role_key in sorted(custom_roles, key=glocale.sort_key):
        if role_key and role_key not in seen:
            roles.append((role_key, role_key))
            seen.add(role_key)

    return roles


# ------------------------
# Help (from the HELP BUTTON BLOCK of help_doc_button.py, see
# HelpDocButton.md; here as a toolbar icon instead of a labeled button)
#
# A click shows the README.md in the Markdown Dash gramplet when that
# addon is installed and active, and otherwise opens the help_url from
# the .gpr.py in the web browser.
# ------------------------
_MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
_MARKDOWNDASH_ID = "markdowndash"
HELP_ICON_NAME = "help-browser"  # from the icon theme, color variant only
#: Full-color help icon bundled in the media folder, used only when the
#: icon theme has no color help-browser icon (instead of its symbolic one).
HELP_ICON_FILE = os.path.join(_MEDIA_DIR, "Gnome-help-browser.svg")

# The toolbar is rebuilt from its XML by every UIManager.update_menu()
# call (for example when Gramps shows or hides actions), so an image set
# from code is lost at the next rebuild. The Help icon therefore goes in the
# XML as an icon name: a private, unique name whose only file is a copy of
# the chosen color icon. No theme has that name, and no "-symbolic" file
# exists for it, so GTK can only ever show that color icon.
_HELP_ICON_DIR = os.path.join(GLib.get_user_cache_dir(), "gramps-eventsbyrole-icons")
_HELP_ICON_STATE = {"source": None, "name": None, "serial": 0}


def _help_icon_source():
    """
    Find the color Help icon to show: the current icon theme help-browser
    icon in its regular (color) variant, or else the bundled SVG. Never a
    symbolic icon. Return the icon file path, or None if neither exists.
    """
    info = Gtk.IconTheme.get_default().lookup_icon(
        HELP_ICON_NAME, 48, Gtk.IconLookupFlags.FORCE_REGULAR
    )
    if info is not None and not info.is_symbolic():
        filename = info.get_filename()
        if filename and os.path.isfile(filename):
            return filename
    if os.path.isfile(HELP_ICON_FILE):
        return HELP_ICON_FILE
    LOG.warning("Events by Role: no full-color Help icon (%s missing)", HELP_ICON_FILE)
    return None


def help_icon_name():
    """
    Return the private icon name for the Help icon, refreshed when the
    chosen source file changes (for example after an icon theme change),
    or "" if no color icon is available, so that no symbolic one shows.
    """
    source = _help_icon_source()
    state = _HELP_ICON_STATE
    if source is None:
        return ""
    if source == state["source"] and state["name"]:
        return state["name"]
    try:
        os.makedirs(_HELP_ICON_DIR, exist_ok=True)
        own_prefix = f"eventsbyrole-help-{os.getpid()}-"
        for old in os.listdir(_HELP_ICON_DIR):  # earlier copies of this process
            if old.startswith(own_prefix):
                os.remove(os.path.join(_HELP_ICON_DIR, old))
        state["serial"] += 1
        # a new name each time, so GTK never serves a cached older image
        name = f"{own_prefix}{state['serial']}"
        extension = os.path.splitext(source)[1].lower() or ".png"
        shutil.copyfile(source, os.path.join(_HELP_ICON_DIR, name + extension))
    except OSError:
        LOG.warning("Events by Role: cannot prepare the Help icon", exc_info=True)
        return ""
    theme = Gtk.IconTheme.get_default()
    if _HELP_ICON_DIR not in theme.get_search_path():
        theme.append_search_path(_HELP_ICON_DIR)
    else:
        # make the theme see the new file
        theme.set_search_path(theme.get_search_path())
    state["source"], state["name"] = source, name
    return name


def find_local_readme(pdata):
    """
    Return the README.md path of a plugin, or None if it has no README of
    any kind (README.md, README_<lang>.md or locale/<lang>/README.md,
    decided by MarkdownUtils when importable).
    """
    if pdata is None or not pdata.fpath:
        return None
    readme_path = os.path.join(pdata.fpath, "README.md")
    try:
        # importable only once Markdown Dash has been loaded
        # pylint: disable-next=import-outside-toplevel,import-error
        from MarkdownUtils import resolve_localized_path  # type: ignore
    except ImportError:
        return readme_path if os.path.isfile(readme_path) else None
    return readme_path if resolve_localized_path(readme_path).exists() else None


def resolve_markdown_dash_opener():
    """
    Return the open_markdown_file() function of Markdown Dash, or None when
    Markdown Dash is deactivated, not registered, fails to load, or lacks it.
    """
    gpm = GuiPluginManager.get_instance()
    if _MARKDOWNDASH_ID in gpm.get_hidden_plugin_ids():
        return None
    pdata = PluginRegister.get_instance().get_plugin(_MARKDOWNDASH_ID)
    if pdata is None or not pdata.fpath:
        return None
    mod = gpm.load_plugin(pdata)
    if not mod:
        return None
    return getattr(mod, "open_markdown_file", None)


def open_help_url(pdata, parent):
    """
    Open the registered help_url of a plugin in the default browser; a
    bare wiki page title is resolved against gramps-project.org.
    """
    help_url = getattr(pdata, "help_url", None)
    if not help_url:
        OkDialog(
            _("No documentation available"),
            _("This plugin has neither a README.md nor a registered help_url."),
            parent=parent,
        )
        return
    full_url = (
        help_url
        if help_url.startswith(("http://", "https://"))
        else "https://gramps-project.org/wiki/index.php?title="
        + quote(help_url, safe=":")
    )
    try:
        Gio.AppInfo.launch_default_for_uri(full_url, None)
    except GLib.Error:
        LOG.exception("help: could not open help_url: %s", full_url)


def own_pdata():
    """Return the PluginData of this view, or None."""
    return PluginRegister.get_instance().get_plugin(PLUGIN_ID)


def help_uses_readme():
    """Return True when a click on Help will show the README in Markdown Dash."""
    # Load Markdown Dash first: that makes MarkdownUtils importable,
    # which find_local_readme() uses to recognize translated READMEs.
    return (
        resolve_markdown_dash_opener() is not None
        and find_local_readme(own_pdata()) is not None
    )


def help_tooltip():
    """Return the Help icon tooltip, saying which documentation a click shows."""
    # One pattern for every view: the translated addon name from the
    # .gpr.py is substituted, so translators see no per-addon strings.
    pdata = own_pdata()
    names = {"addon": pdata.name if pdata is not None else PLUGIN_ID}
    if help_uses_readme():
        return _("View the ReadMe markdown docs for the %(addon)s view mode") % names
    return _("Browse to the Help URL for the %(addon)s view mode") % names


def show_help(uistate):
    """Show the README.md in Markdown Dash when possible, else the help_url."""
    pdata = own_pdata()
    open_markdown_file = resolve_markdown_dash_opener()
    if open_markdown_file is not None:
        readme_path = find_local_readme(pdata)
        if readme_path is not None and pdata is not None:
            open_markdown_file(
                readme_path,
                uistate,
                parent=uistate.window,
                addon_name=pdata.name,
            )
            return
    if pdata is not None:
        open_help_url(pdata, uistate.window)


class EventsByRoleModel(EventModel):
    """Event model with one participant-name column for each role."""

    def __init__(
        self,
        db,
        uistate,
        role_keys,
        scol=0,
        order=None,
        search=None,
        skip=set(),
        sort_map=None,
    ):
        from gi.repository import Gtk

        if order is None:
            order = Gtk.SortType.ASCENDING

        self.role_keys = tuple(role_keys)
        self.role_cache = LRU(config.get("interface.treemodel-cache-size"))
        self.gen_cursor = db.get_event_cursor
        self.map = db.get_raw_event_data
        self.fmap = [
            self.column_description,
            self.column_id,
            self.column_type,
            self.column_date,
            self.column_place,
            self.column_private,
            self.column_tags,
            self.column_change,
        ]
        self.fmap.extend(
            lambda data, role_key=role_key: self.column_role_participants(
                data, role_key
            )
            for role_key in self.role_keys
        )
        self.fmap.append(self.column_tag_color)

        self.smap = [
            self.column_description,
            self.column_id,
            self.column_type,
            self.sort_date,
            self.column_place,
            self.column_private,
            self.column_tags,
            self.sort_change,
        ]
        self.smap.extend(
            lambda data, role_key=role_key: self.column_role_participants(
                data, role_key
            )
            for role_key in self.role_keys
        )
        self.smap.append(self.column_tag_color)

        FlatBaseModel.__init__(
            self,
            db,
            uistate,
            scol,
            order,
            search=search,
            skip=skip,
            sort_map=sort_map,
        )

    def color_column(self):
        """Return the hidden tag-color model column."""
        return len(self.fmap) - 1

    def column_role_participants(self, data, role_key):
        """Return sorted, joined participant names for one role and event."""
        # Gramps 5.2 hands the model a raw tuple; 6.0+ a DataDict.
        handle = data[0] if isinstance(data, (tuple, list)) else data.handle
        if handle not in self.role_cache:
            self.role_cache[handle] = self._participants_by_role(handle)
        return self.role_cache[handle].get(role_key, "")

    def update_row_by_handle(self, handle):
        """Invalidate participant data when an event row is refreshed."""
        if handle in self.role_cache:
            del self.role_cache[handle]
        super().update_row_by_handle(handle)

    def _participants_by_role(self, event_handle):
        """Build the per-event role-to-participant display mapping."""
        by_role = {}
        for class_name, handle in self.db.find_backlink_handles(
            event_handle, include_classes=["Person", "Family"]
        ):
            if class_name == "Person":
                participant = self.db.get_person_from_handle(handle)
                if participant is None:
                    continue
                name = name_displayer.display(participant)
            else:
                participant = self.db.get_family_from_handle(handle)
                if participant is None:
                    continue
                name = family_name(participant, self.db)

            for event_ref in participant.get_event_ref_list():
                if event_ref.ref == event_handle:
                    role_key = event_ref.get_role().xml_str()
                    by_role.setdefault(role_key, {})[(class_name, handle)] = name

        return {
            role_key: "; ".join(sorted(names.values(), key=glocale.sort_key))
            for role_key, names in by_role.items()
        }

    def destroy(self):
        """Release role data cached by this model."""
        self.role_cache = None
        super().destroy()


class EventsByRoleView(EventView):
    """Alternate Events view showing participants grouped by event role."""

    def __init__(self, pdata, dbstate, uistate, nav_group=0):
        self.roles = get_role_columns(dbstate.db)
        self.role_keys = tuple(role_key for role_key, _label in self.roles)
        self.COLUMNS = list(EventView.COLUMNS[:BASE_COLUMN_COUNT]) + [
            (label, TEXT, None) for _role_key, label in self.roles
        ]

        # Blank defaults on purpose: save() comments out values equal to
        # their default, and a commented-out rolekeys or rank would come
        # back as the *current* default, out of step with the other lists.
        # init_config() fills in or remaps the real layout.
        self.CONFIGSETTINGS = (
            ("columns.visible", []),
            ("columns.rank", []),
            ("columns.size", []),
            ("columns.rolekeys", []),
        )

        self._help_tooltip_text = ""
        self.toolbar_ui = None
        # a new icon theme restyles the Help icon too
        Gtk.IconTheme.get_default().connect("changed", self.cb_icon_theme_changed)

        signal_map = {
            "event-add": self.row_add,
            "event-update": self.row_update,
            "event-delete": self.row_delete,
            "event-rebuild": self.object_build,
            "person-update": self.person_update,
            "person-add": self.person_update,
            "person-delete": self.object_build,
            "family-update": self.family_update,
            "family-add": self.family_update,
            "family-delete": self.object_build,
            "place-update": self.related_update,
        }

        ListView.__init__(
            self,
            _("Events by Role"),
            pdata,
            dbstate,
            uistate,
            self._make_model,
            signal_map,
            EventBookmarks,
            nav_group,
            multiple=True,
            filter_class=EventSidebarFilter,
        )

        uistate.connect("nameformat-changed", self.build_tree)
        uistate.connect("placeformat-changed", self.build_tree)
        self.additional_uis.append(self.additional_ui)
        # kept as one list object so a refresh can update it in place
        self.toolbar_ui = self._build_toolbar_ui()
        self.additional_uis.append(self.toolbar_ui)

    def init_config(self):
        """Keep view settings in EventsByRole.ini beside this module."""
        if self._config:
            return
        # __file__ + use_plugins_path=False -> <addon folder>/EventsByRole.ini
        self._config = config.register_manager(
            "EventsByRole", __file__, use_plugins_path=False
        )

        # 1. Defaults. Meta defaults are blank on purpose: save() comments
        #    out values equal to their default, and the meta must stay live.
        self._config.register("meta.plugin_id", "")
        self._config.register("meta.schema_version", "")
        for section, value in self.CONFIGSETTINGS:
            self._config.register(section, value)

        # 2. Stored values overwrite the defaults (or a new file is created).
        self._config.init()

        # 3. Keep the stored values only if this code can read them.
        found = _as_int(self._config.get("meta.schema_version"))
        compatible = (
            self._config.get("meta.plugin_id") == PLUGIN_ID
            and found is not None
            and INI_MIN_COMPATIBLE <= found <= INI_SCHEMA_VERSION
        )
        if not compatible:
            # Wrong owner, unversioned, too old, or newer than this code:
            # back to defaults. reset() also drops keys no longer registered.
            self._config.reset()
        elif found < INI_SCHEMA_VERSION:
            # Readable but older: migrate step by step here, e.g.
            # if found < 2: rename or convert a setting
            pass

        # 4. Stamp the file as current; it is written on PageView.on_delete().
        self._config.set("meta.plugin_id", PLUGIN_ID)
        self._config.set("meta.schema_version", str(INI_SCHEMA_VERSION))

        # 5. Make the column layout match this tree's role set.
        stored_keys = self._config.get("columns.rolekeys")
        if not self._column_config_is_valid(stored_keys):
            self._reset_column_config()
        elif list(stored_keys) != list(self.role_keys):
            self._remap_column_config(stored_keys)
        self.config_connect()

    @staticmethod
    def _column_ids(role_keys):
        """Return a stable identity for each model column."""
        return [f"base:{index}" for index in range(BASE_COLUMN_COUNT)] + [
            f"role:{role_key}" for role_key in role_keys
        ]

    def _column_config_is_valid(self, stored_keys):
        """Return True if the stored layout is complete and self-consistent."""
        rank = self._config.get("columns.rank")
        size = self._config.get("columns.size")
        visible = self._config.get("columns.visible")
        if not stored_keys or not isinstance(stored_keys, list):
            return False
        total = BASE_COLUMN_COUNT + len(stored_keys)
        return (
            len(rank) == len(size) == total
            and sorted(rank) == list(range(total))
            and all(isinstance(col, int) and 0 <= col < total for col in visible)
        )

    def _write_column_config(self, rank, size, visible):
        """Store a column layout for the current role set."""
        self._config.set("columns.rank", rank)
        self._config.set("columns.size", size)
        self._config.set("columns.visible", visible)
        self._config.set("columns.rolekeys", list(self.role_keys))

    def _make_model(
        self,
        db,
        model_uistate,
        scol=0,
        order=None,
        search=None,
        skip=set(),
        sort_map=None,
    ):
        """Create a model using the view's current role columns."""
        return EventsByRoleModel(
            db,
            model_uistate,
            self.role_keys,
            scol=scol,
            order=order,
            search=search,
            skip=skip,
            sort_map=sort_map,
        )

    def _reset_column_config(self):
        """Store the default layout: every column visible, in model order."""
        indexes = list(range(len(self.COLUMNS)))
        sizes = BASE_COLUMN_SIZES + [ROLE_COLUMN_SIZE] * len(self.role_keys)
        self._write_column_config(indexes, sizes, list(indexes))

    def _remap_column_config(self, old_role_keys):
        """
        Carry the user's column order, widths and visibility over to a new
        role set. Columns for roles that disappeared are dropped; columns
        for new roles are appended, visible, at the default width.
        """
        old_ids = self._column_ids(old_role_keys)
        new_index = {
            col_id: index
            for index, col_id in enumerate(self._column_ids(self.role_keys))
        }
        old_visible = set(self._config.get("columns.visible"))
        rank, size, visible = [], [], []
        for old_col, width in zip(
            self._config.get("columns.rank"), self._config.get("columns.size")
        ):
            new_col = new_index.get(old_ids[old_col])
            if new_col is None or new_col in rank:
                continue
            rank.append(new_col)
            size.append(width)
            if old_col in old_visible:
                visible.append(new_col)
        for new_col in new_index.values():
            if new_col not in rank:
                rank.append(new_col)
                size.append(ROLE_COLUMN_SIZE)
                visible.append(new_col)
        self._write_column_config(rank, size, visible)

    def _refresh_role_columns(self, db=None, rebuild=True):
        """
        Update the role columns if the role set changed (custom roles added
        or removed, or another tree opened). Return True if it changed.
        """
        roles = get_role_columns(db if db is not None else self.dbstate.db)
        role_keys = tuple(role_key for role_key, _label in roles)
        if role_keys == self.role_keys:
            return False

        old_role_keys = list(self.role_keys)
        self.roles = roles
        self.role_keys = role_keys
        self.COLUMNS = list(EventView.COLUMNS[:BASE_COLUMN_COUNT]) + [
            (label, TEXT, None) for _role_key, label in roles
        ]
        self._remap_column_config(old_role_keys)

        # The TreeView columns point at model indexes, so they must be
        # rebuilt too. Detach the old model first so GTK never renders new
        # columns against it. self.list only exists once the view is built.
        if getattr(self, "list", None) is not None:
            self.list.set_model(None)
            self.build_columns()
        self.dirty = True
        if rebuild and self.active:
            self.build_tree(preserve_col=False)
        return True

    def change_db(self, db):
        """Pick up the new tree's custom roles before the normal rebuild."""
        self._refresh_role_columns(db, rebuild=False)
        super().change_db(db)

    def person_update(self, handle_list):
        """Refresh role columns and affected events after person changes."""
        if not self._refresh_role_columns():
            EventView.person_update(self, handle_list)

    def family_update(self, handle_list):
        """Refresh role columns and affected events after family changes."""
        if not self._refresh_role_columns():
            EventView.family_update(self, handle_list)

    # ---------------------------------------------------------------
    # toolbar: Help icon
    # ---------------------------------------------------------------
    def define_actions(self):
        """Add the toolbar Help action to the Events view actions."""
        EventView.define_actions(self)
        self.action_list.append(("EventsByRoleHelp", self.cb_show_help))

    def change_page(self):
        """The view is shown: pick up README and Markdown Dash changes."""
        EventView.change_page(self)
        # README / Markdown Dash may have changed since the toolbar was
        # built. The toolbar is rebuilt from XML at every update_menu(), so
        # the tooltip must change in the XML, not on the current widget.
        if help_tooltip() != self._help_tooltip_text:
            self._refresh_toolbar_ui()

    def _build_toolbar_ui(self):
        """Return the toolbar XML with the Help icon, as a one-element list."""
        self._help_tooltip_text = help_tooltip()
        toolbar = f"""
    <placeholder id="MoreButtons">
    <child>
      <object class="GtkToolItem">
        <child>
          <object class="GtkButton" id="EventsByRoleHelpButton">
            <property name="action-name">win.EventsByRoleHelp</property>
            <property name="tooltip_text">{escape(self._help_tooltip_text)}</property>
            <property name="relief">GTK_RELIEF_NONE</property>
            <child>
              <object class="GtkImage">
                <property name="visible">True</property>
                <property name="icon-name">{escape(help_icon_name())}</property>
                <property name="icon_size">3</property>
              </object>
            </child>
          </object>
        </child>
      </object>
    </child>
    </placeholder>
    """
        return [toolbar]

    def cb_icon_theme_changed(self, *_args):
        """
        The icon theme changed: when the chosen Help icon file changes, put
        the new private icon name in the toolbar XML.
        """
        if self.toolbar_ui is None:
            return  # toolbar not built yet; it will use the new icon
        old_name = _HELP_ICON_STATE["name"]
        if help_icon_name() != old_name:
            self._refresh_toolbar_ui()

    def _refresh_toolbar_ui(self):
        """Rebuild the toolbar XML; merge it now if this view is shown."""
        if self.toolbar_ui is None:
            return
        self.toolbar_ui[:] = self._build_toolbar_ui()
        if self.active:
            self.uimanager.add_ui_from_string(self.toolbar_ui)
            self.uimanager.update_menu()

    def cb_show_help(self, *_args):
        """The toolbar Help icon: show the documentation."""
        show_help(self.uistate)

    def get_config_name(self):
        """Lowercase: PersistentTreeView stores this as a gramps.ini key."""
        return "eventsbyrole"
