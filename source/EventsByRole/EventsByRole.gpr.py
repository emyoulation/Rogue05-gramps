#
# Gramps - a GTK+/GNOME based genealogy program
# Copyright 2026     Wojciech Sopot (Rogue05)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#

"""Registration for the Events by Role view."""

from gramps.version import VERSION_TUPLE, major_version


if (5, 2, 0) <= VERSION_TUPLE < (6, 2, 0):
    register(
        VIEW,
        id="eventsbyrole",
        name=_("Events by Role"),
        description=_(
            "An Events view that displays participants in separate columns "
            "for each event role."
        ),
        authors=["Wojciech Sopot"],
        version="1.0.2",  # build 20261102.2105
        gramps_target_version=major_version,
        status=STABLE,
        fname="EventsByRole.py",
        viewclass="EventsByRoleView",
        category=("Events", _("Events")),
        stock_icon="gramps-tree-list",
        help_url=(
            "https://github.com/Rogue05/Gramps-filter/"
            "blob/main/source/EventsByRole/README.md"
        ),
    )
