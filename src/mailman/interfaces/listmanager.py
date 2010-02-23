# Copyright (C) 2007-2010 by the Free Software Foundation, Inc.
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

"""Interface for list storage, deleting, and finding."""

from __future__ import absolute_import, unicode_literals

__metaclass__ = type
__all__ = [
    'IListManager',
    'ListAlreadyExistsError',
    'NoSuchListError',
    ]


from zope.interface import Interface, Attribute

from mailman.interfaces.errors import MailmanError
from mailman.interfaces.mailinglist import IMailingList



class ListAlreadyExistsError(MailmanError):
    """Attempted to create a mailing list that already exists.

    Mailing list objects must be uniquely named by their fully qualified list
    name.
    """


class NoSuchListError(MailmanError):
    """Attempt to access a mailing list that does not exist."""

    def __init__(self, fqdn_listname):
        self.fqdn_listname = fqdn_listname

    def __str__(self):
        return 'No such mailing list: {0.fqdn_listname}'.format(self)




class IListManager(Interface):
    """The interface of the global list manager.

    The list manager manages `IMailingList` objects.  You can add and remove
    `IMailingList` objects from the list manager, and you can retrieve them
    from the manager via their fully qualified list name, e.g.:
    `mylist@example.com`.
    """

    def create(fqdn_listname):
        """Create a mailing list with the given name.

        :type fqdn_listname: Unicode
        :param fqdn_listname: The fully qualified name of the mailing list,
            e.g. `mylist@example.com`.
        :return: The newly created `IMailingList`.
        :raise `ListAlreadyExistsError` if the named list already exists.
        """

    def get(fqdn_listname):
        """Return the mailing list with the given name, if it exists.

        :type fqdn_listname: Unicode.
        :param fqdn_listname: The fully qualified name of the mailing list.
        :return: the matching `IMailingList` or None if the named list does
            not exist.
        """

    def delete(mlist):
        """Remove the mailing list from the database.

        :type mlist: `IMailingList`
        :param mlist: The mailing list to delete.
        """

    mailing_lists = Attribute(
        """An iterator over all the mailing list objects managed by this list
        manager.""")

    names = Attribute(
        """An iterator over the fully qualified list names of all mailing
        lists managed by this list manager.""")

    def get_mailing_lists():
        """The list of all mailing lists.

        :return: The list of all known mailing lists.
        :rtype: list of `IMailingList`
        """

    def new(fqdn_listname):
        """Add a new maling list.

        The mailing may not exist yet, but the domain specified in
        `fqdn_listname` must exist.

        :param fqdn_listname: The fully qualified name for the new
            mailing list.
        :type fqdn_listname: string
        :return: The new mailing list
        :rtype: `IMailingList`
        :raises `BadDomainSpecificationError`: when the hostname part of
            `fqdn_listname` does not exist.
        :raises `ListAlreadyExistsError`: when the mailing list already
            exists.
        """
