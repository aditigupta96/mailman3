# Copyright (C) 2014-2015 by the Free Software Foundation, Inc.
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

"""Test MTA connections."""

__all__ = [
    'TestConnection',
    ]


import unittest

from mailman.config import config
from mailman.mta.connection import Connection
from mailman.testing.layers import SMTPLayer
from smtplib import SMTPAuthenticationError



class TestConnection(unittest.TestCase):
    layer = SMTPLayer

    def test_authentication_error(self):
        # Logging in to the MTA with a bad user name and password produces a
        # 571 Bad Authentication error.
        with self.assertRaises(SMTPAuthenticationError) as cm:
            connection = Connection(
                config.mta.smtp_host, int(config.mta.smtp_port), 0,
                'baduser', 'badpass')
            connection.sendmail('anne@example.com', ['bart@example.com'], """\
From: anne@example.com
To: bart@example.com
Subject: aardvarks

""")
        self.assertEqual(cm.exception.smtp_code, 571)
        self.assertEqual(cm.exception.smtp_error, b'Bad authentication')
