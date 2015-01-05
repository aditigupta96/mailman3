# Copyright (C) 2009-2015 by the Free Software Foundation, Inc.
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

"""The content filter."""

__all__ = [
    'ContentFilter'
    ]


from mailman.database.model import Model
from mailman.database.types import Enum
from mailman.interfaces.mime import IContentFilter, FilterType
from sqlalchemy import Column, ForeignKey, Integer, Unicode
from sqlalchemy.orm import relationship
from zope.interface import implementer



@implementer(IContentFilter)
class ContentFilter(Model):
    """A single filter criteria."""

    __tablename__ = 'contentfilter'

    id = Column(Integer, primary_key=True)

    mailing_list_id = Column(Integer, ForeignKey('mailinglist.id'), index=True)
    mailing_list = relationship('MailingList')

    filter_type = Column(Enum(FilterType))
    filter_pattern = Column(Unicode)

    def __init__(self, mailing_list, filter_pattern, filter_type):
        self.mailing_list = mailing_list
        self.filter_pattern = filter_pattern
        self.filter_type = filter_type
