#
# Gramps - a GTK+/GNOME based genealogy program
# Copyright 2026     Wojciech Sopot (Rogue05)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#

"""Registration for the People with Event ID filter rule."""

from gramps.version import VERSION_TUPLE, major_version


if (5, 2, 0) <= VERSION_TUPLE < (6, 2, 0):
    register(
        RULE,
        id="PeopleWithEventId",
        name=_("People with event ID"),
        description=_(
            "Matches people who participated in the event with the specified "
            "Gramps ID, regardless of their role."
        ),
        authors=["Wojciech Sopot"],
        version="1.0.1",
        gramps_target_version=major_version,
        status=STABLE,
        fname="EventParticipantsById.py",
        ruleclass="PeopleWithEventId",
        namespace="Person",
        help_url="https://github.com/Rogue05/Gramps-filter#readme",
    )
