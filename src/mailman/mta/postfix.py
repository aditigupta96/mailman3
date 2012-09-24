# Copyright (C) 2001-2012 by the Free Software Foundation, Inc.
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

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = [
    'LMTP',
    ]


import os
import logging

from flufl.lock import Lock
from operator import attrgetter
from zope.component import getUtility
from zope.interface import implementer

from mailman.config import config
from mailman.interfaces.listmanager import IListManager
from mailman.interfaces.mta import (
    IMailTransportAgentAliases, IMailTransportAgentLifecycle)
from mailman.utilities.datetime import now


log = logging.getLogger('mailman.error')
ALIASTMPL = '{0:{2}}lmtp:[{1.mta.lmtp_host}]:{1.mta.lmtp_port}'



class _FakeList:
    """Duck-typed list for the `IMailTransportAgentAliases` interface."""

    def __init__(self, list_name, mail_host):
        self.list_name = list_name
        self.mail_host = mail_host
        self.posting_address = '{0}@{1}'.format(list_name, mail_host)



@implementer(IMailTransportAgentLifecycle)
class LMTP:
    """Connect Mailman to Postfix via LMTP."""

    def create(self, mlist):
        """See `IMailTransportAgentLifecycle`."""
        # We can ignore the mlist argument because for LMTP delivery, we just
        # generate the entire file every time.
        self.regenerate()
        self.regenerate_domain()

    delete = create

    def regenerate(self, output=None):
        """See `IMailTransportAgentLifecycle`.

        The format for Postfix's LMTP transport map is defined here:
        http://www.postfix.org/transport.5.html
        """
        # Acquire a lock file to prevent other processes from racing us here.
        lock_file = os.path.join(config.LOCK_DIR, 'mta')
        with Lock(lock_file):
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

    def regenerate_domain(self, output=None):
        """The map for all list domains

        The format for Postfix's LMTP transport map is defined here:
        http://www.postfix.org/transport.5.html
        """
        # Acquire a lock file to prevent other processes from racing us here.
        lock_file = os.path.join(config.LOCK_DIR, 'mta')
        with Lock(lock_file):
            # If output is a filename, open up a backing file and write the
            # output there, then do the atomic rename dance.  First though, if
            # it's None, we use a calculated path.
            if output is None:
                path = os.path.join(config.DATA_DIR, 'postfix_domains')
                path_new = path + '.new'
            elif isinstance(output, basestring):
                path = output
                path_new = output + '.new'
            else:
                path = path_new = None
            if path_new is None:
                self._do_write_file_domains(output)
                # There's nothing to rename, and we can't generate the .db
                # file, so we're done.
                return
            # Write the file.
            with open(path_new, 'w') as fp:
                self._do_write_file_domains(fp)
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
        # Sort all existing mailing list names first by domain, then by local
        # part.  For postfix we need a dummy entry for the domain.
        list_manager = getUtility(IListManager)
        by_domain = {}
        for list_name, mail_host in list_manager.name_components:
            mlist = _FakeList(list_name, mail_host)
            by_domain.setdefault(mlist.mail_host, []).append(mlist)
        print("""\
# AUTOMATICALLY GENERATED BY MAILMAN ON {0}
#
# This file is generated by Mailman, and is kept in sync with the binary hash
# file.  YOU SHOULD NOT MANUALLY EDIT THIS FILE unless you know what you're
# doing, and can keep the two files properly in sync.  If you screw it up,
# you're on your own.
""".format(now().replace(microsecond=0)), file=fp)
        sort_key = attrgetter('list_name')
        for domain in sorted(by_domain):
            print("""\
# Aliases which are visible only in the @{0} domain.""".format(domain),
                file=fp)
            for mlist in sorted(by_domain[domain], key=sort_key):
                utility = getUtility(IMailTransportAgentAliases)
                aliases = list(utility.aliases(mlist))
                width = max(len(alias) for alias in aliases) + 3
                print(ALIASTMPL.format(aliases.pop(0), config, width), file=fp)
                for alias in aliases:
                    print(ALIASTMPL.format(alias, config, width), file=fp)
                print(file=fp)

    def _do_write_file_domains(self, fp):
        """Do the actual file writes of the domain map for list creation."""
        # Sort all existing mailing list names first by domain, then my local
        # part.  For postfix we need a dummy entry for the domain.
        by_domain = []
        for list_name, mail_host in getUtility(IListManager).name_components:
            by_domain.append(mail_host)
        print("""\
# AUTOMATICALLY GENERATED BY MAILMAN ON {0}
#
# This file is generated by Mailman, and is kept in sync with the binary hash
# file.  YOU SHOULD NOT MANUALLY EDIT THIS FILE unless you know what you're
# doing, and can keep the two files properly in sync.  If you screw it up,
# you're on your own.
""".format(now().replace(microsecond=0)), file=fp)
        for domain in sorted(by_domain):
            print("""{0} {0}""".format(domain), file=fp)

