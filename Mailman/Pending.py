# Copyright (C) 1998,1999,2000,2001 by the Free Software Foundation, Inc.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software 
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.

""" Track pending confirmation of subscriptions.

new(stuff...) places an item's data in the db, returning its cookie.

confirmed(cookie) returns a tuple for the data, removing the item
from the db.  It returns None if the cookie is not registered.
"""

import os
import time
import sha
import marshal
import random
import errno

from Mailman import mm_cfg
from Mailman import LockFile

DBFILE = os.path.join(mm_cfg.DATA_DIR, 'pending.db')
LOCKFILE = os.path.join(mm_cfg.LOCK_DIR, 'pending.lock')

# Types of pending records
SUBSCRIPTION = 'S'
UNSUBSCRIPTION = 'U'
CHANGE_OF_ADDRESS = 'C'
HELD_MESSAGE = 'H'

_ALLKEYS = [(x,) for x in (SUBSCRIPTION, UNSUBSCRIPTION,
                           CHANGE_OF_ADDRESS, HELD_MESSAGE,
                           )]



def new(*content):
    """Create a new entry in the pending database, returning cookie for it."""
    # It's a programming error if this assertion fails!  We do it this way so
    # the assert test won't fail if the sequence is empty.
    assert content[:1] in _ALLKEYS
    # Acquire the pending database lock, letting TimeOutError percolate up.
    lock = LockFile.LockFile(LOCKFILE)
    lock.lock(timeout=30)
    try:
        # Load the current database
        db = _load()
        # Calculate a unique cookie
        while 1:
            n = random.random()
            now = time.time()
            hashfood = str(now) + str(n) + str(content)
            cookie = sha.new(hashfood).hexdigest()
            if not db.has_key(cookie):
                break
        # Store the content, plus the time in the future when this entry will
        # be evicted from the database, due to staleness.
        db[cookie] = content
        evictions = db.setdefault('evictions', {})
        evictions[cookie] = now + mm_cfg.PENDING_REQUEST_LIFE
        _save(db)
        return cookie
    finally:
        lock.unlock()



def confirm(cookie, expunge=1):
    """Return data for cookie, or None if not found.

    If optional expunge is true (the default), the record is also removed from
    the database.
    """
    # Acquire the pending database lock, letting TimeOutError percolate up.
    # BAW: we perhaps shouldn't acquire the lock if expunge==0.
    lock = LockFile.LockFile(LOCKFILE)
    lock.lock(timeout=30)
    try:
        # Load the database
        db = _load()
        missing = []
        content = db.get(cookie, missing)
        if content is missing:
            return None
        # Remove the entry from the database
        if expunge:
            del db[cookie]
            del db['evictions'][cookie]
            _save(db)
        return content
    finally:
        lock.unlock()



def _load():
    # Lock must be acquired.
    try:
        fp = open(DBFILE)
        return marshal.load(fp)
    except IOError, e:
        if e.errno <> errno.ENOENT: raise
        # No database yet, so initialize a fresh one
        return {'evictions': {}}


def _save(db):
    # Lock must be acquired.
    evictions = db['evictions']
    now = time.time()
    for cookie, data in db.items():
        if cookie in ('evictions', 'version'):
            continue
        timestamp = evictions[cookie]
        if now > timestamp:
            # The entry is stale, so remove it.
            del db[cookie]
            del evictions[cookie]
    # Clean out any bogus eviction entries.
    for cookie in evictions.keys():
        if not db.has_key(cookie):
            del evictions[cookie]
    db['version'] = mm_cfg.PENDING_FILE_SCHEMA_VERSION
    omask = os.umask(007)
    try:
        fp = open(DBFILE, 'w')
        marshal.dump(db, fp)
        fp.close()
    finally:
        os.umask(omask)



def _update(olddb):
    # Update an old pending_subscriptions.db database to the new format
    lock = LockFile.LockFile(LOCKFILE)
    lock.lock(timeout=30)
    try:
        # We don't need this entry anymore
        if olddb.has_key('lastculltime'):
            del olddb['lastculltime']
        db = _load()
        evictions = db.setdefault('evictions', {})
        for cookie, data in olddb.items():
            # The cookies used to be kept as a 6 digit integer.  We now keep
            # the cookies as a string (sha in our case, but it doesn't matter
            # for cookie matching).
            cookie = str(cookie)
            # The old format kept the content as a tuple and tacked the
            # timestamp on as the last element of the tuple.  We keep the
            # timestamps separate, but require the prepending of a record type
            # indicator.  We know that the only things that were kept in the
            # old format were subscription requests.  Also, the old request
            # format didn't have the subscription language.  Best we can do
            # here is use the server default.
            db[cookie] = (SUBSCRIPTION,) + data[:-1] + \
                         (mm_cfg.DEFAULT_SERVER_LANGUAGE,)
            # The old database format kept the timestamp as the time the
            # request was made.  The new format keeps it as the time the
            # request should be evicted.
            evictions[cookie] = data[-1] + mm_cfg.PENDING_REQUEST_LIFE
        _save(db)
    finally:
        lock.unlock()
