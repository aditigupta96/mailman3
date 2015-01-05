# Copyright (C) 2007-2015 by the Free Software Foundation, Inc.
#
# This file is part of GNU Mailman.
#
# GNU Mailman is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# GNU Mailman is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along with
# GNU Mailman.  If not, see <http://www.gnu.org/licenses/>.

"""The no-Subject header rule."""

__all__ = [
    'NoSubject',
    ]


from mailman.core.i18n import _
from mailman.interfaces.rules import IRule
from zope.interface import implementer



@implementer(IRule)
class NoSubject:
    """The no-Subject rule."""

    name = 'no-subject'
    description = _('Catch messages with no, or empty, Subject headers.')
    record = True

    def check(self, mlist, msg, msgdata):
        """See `IRule`."""
        subject = msg.get('subject', '').strip()
        return subject == ''
