#
# Gramps - a GTK+/GNOME based genealogy program
# Copyright 2026     Wojciech Sopot (Rogue05)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#

"""Person filter rule for participants in an event identified by Gramps ID."""

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.filters.rules import Rule

_ = glocale.translation.gettext


class PeopleWithEventId(Rule):
    """Match people who reference the event with the requested Gramps ID."""

    labels = [_("Event Gramps ID:")]
    name = _("People with event ID")
    description = _(
        "Matches every person who participated in the event with the specified "
        "Gramps ID, regardless of their role."
    )
    category = _("Event filters")

    def __init__(self, arg, use_regex=False, use_case=False):
        """Initialize the rule and its per-run event handle."""
        super().__init__(arg, use_regex, use_case)
        self.event_handle = None

    def prepare(self, db, user):
        """Resolve the supplied Gramps ID once before filtering people."""
        self.event_handle = None
        if not self.list or not self.list[0]:
            return

        event_id = self.list[0].strip()
        if event_id:
            event = db.get_event_from_gramps_id(event_id)
            if event is not None:
                self.event_handle = event.handle

    def reset(self):
        """Release the resolved handle after the filter run."""
        self.event_handle = None

    def apply_to_one(self, db, person):
        """Return whether this person references the selected event."""
        if self.event_handle is None:
            return False
        return any(
            event_ref.ref == self.event_handle
            for event_ref in person.get_event_ref_list()
        )

    # Gramps 5.2 invokes apply(); newer versions invoke apply_to_one().
    apply = apply_to_one
