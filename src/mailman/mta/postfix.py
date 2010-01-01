# Copyright (C) 2001-2010 by the Free Software Foundation, Inc.
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

"""Creation/deletion hooks for the Postfix MTA."""

from __future__ import absolute_import, unicode_literals

__metaclass__ = type
__all__ = [
    'LMTP',
    ]


import os
import grp
import pwd
import time
import errno
import logging
import datetime

from locknix.lockfile import Lock
from zope.component import getUtility
from zope.interface import implements

from mailman import Utils
from mailman.config import config
from mailman.core.i18n import _
from mailman.interfaces.listmanager import IListManager
from mailman.interfaces.mta import IMailTransportAgentAliases

log = logging.getLogger('mailman.error')

LOCKFILE = os.path.join(config.LOCK_DIR, 'mta')
SUBDESTINATIONS = (
    'bounces',  'confirm',  'join',         'leave',
    'owner',    'request',  'subscribe',    'unsubscribe',
    )



class LMTP:
    """Connect Mailman to Postfix via LMTP."""

    implements(IMailTransportAgentAliases)

    def create(self, mlist):
        """See `IMailTransportAgentAliases`."""
        # We can ignore the mlist argument because for LMTP delivery, we just
        # generate the entire file every time.
        self.regenerate()

    delete = create

    def regenerate(self, output=None):
        """See `IMailTransportAgentAliases`.

        The format for Postfix's LMTP transport map is defined here:
        http://www.postfix.org/transport.5.html
        """
        # Acquire a lock file to prevent other processes from racing us here.
        with Lock(LOCKFILE):
            # If output is a filename, open up a backing file and write the
            # output there, then do the atomic rename dance.  First though, if
            # it's None, we use a calculated path.
            if output is None:
                path = os.path.join(config.DATA_DIR, 'postfix_lmtp')
                path_new = path + '.new'
            elif isinstance(output, basestring):
                path = output
                path_new = output + '.new'
            else:
                path = path_new = None
            if path_new is None:
                self._do_write_file(output)
                # There's nothing to rename, and we can't generate the .db
                # file, so we're done.
                return
            # Write the file.
            with open(path_new, 'w') as fp:
                self._do_write_file(fp)
            # Atomically rename to the intended path.
            os.rename(path + '.new', path)
            # Now that the new file is in place, we must tell Postfix to
            # generate a new .db file.
            command = config.mta.postfix_map_cmd + ' ' + path
            status = (os.system(command) >> 8) & 0xff
            if status:
                msg = 'command failure: %s, %s, %s'
                errstr = os.strerror(status)
                log.error(msg, command, status, errstr)
                raise RuntimeError(msg % (command, status, errstr))

    def _do_write_file(self, fp):
        """Do the actual file writes for list creation."""
        # Sort all existing mailing list names first by domain, then my local
        # part.  For postfix we need a dummy entry for the domain.
        by_domain = {}
        for mailing_list in getUtility(IListManager).mailing_lists:
            by_domain.setdefault(mailing_list.host_name, []).append(
                mailing_list.list_name)
        print >> fp, """\
# AUTOMATICALLY GENERATED BY MAILMAN ON {0}
#
# This file is generated by Mailman, and is kept in sync with the binary hash
# file.  YOU SHOULD NOT MANUALLY EDIT THIS FILE unless you know what you're
# doing, and can keep the two files properly in sync.  If you screw it up,
# you're on your own.
""".format(datetime.datetime.now().replace(microsecond=0))
        for domain in sorted(by_domain):
            print >> fp, """\
# Aliases which are visible only in the @{0} domain.
""".format(domain)
            for list_name in by_domain[domain]:
                # Calculate the field width of the longest alias.  10 ==
                # len('-subscribe') + '@'.
                longest = len(list_name + domain) + 10
                print >> fp, """\
{0}@{1:{3}}lmtp:[{2.mta.lmtp_host}]:{2.mta.lmtp_port}""".format(
                    list_name, domain, config,
                    # Add 1 because the bare list name has no dash.
                    longest + 1)
            for destination in SUBDESTINATIONS:
                print >> fp, """\
{0}-{1}@{2:{4}}lmtp:[{3.mta.lmtp_host}]:{3.mta.lmtp_port}""".format(
                    list_name, destination, domain, config,
                    longest - len(destination))
            print >> fp
