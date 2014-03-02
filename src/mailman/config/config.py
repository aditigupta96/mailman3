# Copyright (C) 2006-2014 by the Free Software Foundation, Inc.
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

"""Configuration file loading and management."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = [
    'Configuration',
    'external_configuration',
    'load_external'
    ]


import os
import sys

from ConfigParser import SafeConfigParser
from flufl.lock import Lock
from lazr.config import ConfigSchema, as_boolean
from pkg_resources import resource_filename, resource_stream, resource_string
from string import Template
from zope.component import getUtility
from zope.event import notify
from zope.interface import implementer

import mailman.templates

from mailman import version
from mailman.interfaces.configuration import (
    ConfigurationUpdatedEvent, IConfiguration, MissingConfigurationFileError)
from mailman.interfaces.languages import ILanguageManager
from mailman.utilities.filesystem import makedirs
from mailman.utilities.modules import call_name


SPACE = ' '

MAILMAN_CFG_TEMPLATE = """\
# AUTOMATICALLY GENERATED BY MAILMAN ON {}
#
# This is your GNU Mailman 3 configuration file.  You can edit this file to
# configure Mailman to your needs, and Mailman will never overwrite it.
# Additional configuration information is (for now) available in the
# schema.cfg file <http://tinyurl.com/cm5rtqe> and the base mailman.cfg file
# <http://tinyurl.com/dx9b8eg>.
#
# For example, uncomment the following lines to run Mailman in developer mode.
#
# [devmode]
# enabled: yes
# recipient: your.address@your.domain"""



@implementer(IConfiguration)
class Configuration:
    """The core global configuration object."""

    def __init__(self):
        self.switchboards = {}
        self.QFILE_SCHEMA_VERSION = version.QFILE_SCHEMA_VERSION
        self._config = None
        self.filename = None
        # Whether to create run-time paths or not.  This is for the test
        # suite, which will set this to False until the test layer is set up.
        self.create_paths = True
        # Create various registries.
        self.chains = {}
        self.rules = {}
        self.handlers = {}
        self.pipelines = {}
        self.commands = {}
        self.password_context = None

    def _clear(self):
        """Clear the cached configuration variables."""
        self.switchboards.clear()
        getUtility(ILanguageManager).clear()

    def __getattr__(self, name):
        """Delegate to the configuration object."""
        return getattr(self._config, name)

    def load(self, filename=None):
        """Load the configuration from the schema and config files."""
        schema_file = config_file = None
        try:
            schema_file = resource_stream('mailman.config', 'schema.cfg')
            schema = ConfigSchema('schema.cfg', schema_file)
            # If a configuration file was given, load it now too.  First, load
            # the absolute minimum default configuration, then if a
            # configuration filename was given by the user, push it.
            config_file = resource_stream('mailman.config', 'mailman.cfg')
            self._config = schema.loadFile(config_file, 'mailman.cfg')
            if filename is not None:
                self.filename = filename
                with open(filename) as user_config:
                    self._config.push(filename, user_config.read())
        finally:
            if schema_file:
                schema_file.close()
            if config_file:
                config_file.close()
        self._post_process()

    def push(self, config_name, config_string):
        """Push a new configuration onto the stack."""
        self._clear()
        self._config.push(config_name, config_string)
        self._post_process()

    def pop(self, config_name):
        """Pop a configuration from the stack."""
        self._clear()
        self._config.pop(config_name)
        self._post_process()

    def _post_process(self):
        """Perform post-processing after loading the configuration files."""
        # Expand and set up all directories.
        self._expand_paths()
        self.ensure_directories_exist()
        notify(ConfigurationUpdatedEvent(self))

    def _expand_paths(self):
        """Expand all configuration paths."""
        # Set up directories.
        bin_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
        # Now that we've loaded all the configuration files we're going to
        # load, set up some useful directories based on the settings in the
        # configuration file.
        layout = 'paths.' + self._config.mailman.layout
        for category in self._config.getByCategory('paths'):
            if category.name == layout:
                break
        else:
            print('No path configuration found:', layout, file=sys.stderr)
            sys.exit(1)
        # First, collect all variables in a substitution dictionary.  $VAR_DIR
        # is taken from the environment or from the configuration file if the
        # environment is not set.  Because the var_dir setting in the config
        # file could be a relative path, and because 'bin/mailman start'
        # chdirs to $VAR_DIR, without this subprocesses bin/master and
        # bin/runner will create $VAR_DIR hierarchies under $VAR_DIR when that
        # path is relative.
        var_dir = os.environ.get('MAILMAN_VAR_DIR', category.var_dir)
        substitutions = dict(
            argv                    = bin_dir,
            # Directories.
            bin_dir                 = category.bin_dir,
            data_dir                = category.data_dir,
            etc_dir                 = category.etc_dir,
            ext_dir                 = category.ext_dir,
            list_data_dir           = category.list_data_dir,
            lock_dir                = category.lock_dir,
            log_dir                 = category.log_dir,
            messages_dir            = category.messages_dir,
            archive_dir             = category.archive_dir,
            queue_dir               = category.queue_dir,
            var_dir                 = var_dir,
            template_dir            = (
                os.path.dirname(mailman.templates.__file__)
                if category.template_dir == ':source:'
                else category.template_dir),
            # Files.
            lock_file               = category.lock_file,
            pid_file                = category.pid_file,
            )
        # Now, perform substitutions recursively until there are no more
        # variables with $-vars in them, or until substitutions are not
        # helping any more.
        last_dollar_count = 0
        while True:
            # Mutate the dictionary during iteration.
            dollar_count = 0
            for key in substitutions.keys():
                raw_value = substitutions[key]
                value = Template(raw_value).safe_substitute(substitutions)
                if '$' in value:
                    # Still more work to do.
                    dollar_count += 1
                substitutions[key] = value
            if dollar_count == 0:
                break
            if dollar_count == last_dollar_count:
                print('Path expansion infloop detected', file=sys.stderr)
                sys.exit(1)
            last_dollar_count = dollar_count
        # Ensure that all paths are normalized and made absolute.  Handle the
        # few special cases first.  Most of these are due to backward
        # compatibility.
        self.PID_FILE = os.path.abspath(substitutions.pop('pid_file'))
        for key in substitutions:
            attribute = key.upper()
            setattr(self, attribute, os.path.abspath(substitutions[key]))

    @property
    def logger_configs(self):
        """Return all log config sections."""
        return self._config.getByCategory('logging', [])

    @property
    def paths(self):
        """Return a substitution dictionary of all path variables."""
        return dict((k, self.__dict__[k])
                    for k in self.__dict__
                    if k.endswith('_DIR'))

    def ensure_directories_exist(self):
        """Create all path directories if they do not exist."""
        if self.create_paths:
            for variable, directory in self.paths.items():
                makedirs(directory)
            # Avoid circular imports.
            from mailman.utilities.datetime import now
            # Create a mailman.cfg template file if it doesn't already exist.
            # LBYL: <boo hiss>, but it's probably okay because the directories
            # likely didn't exist before the above loop, and we'll create a
            # temporary lock.
            lock_file = os.path.join(self.LOCK_DIR, 'mailman-cfg.lck')
            mailman_cfg = os.path.join(self.ETC_DIR, 'mailman.cfg')
            with Lock(lock_file):
                if not os.path.exists(mailman_cfg):
                    with open(mailman_cfg, 'w') as fp:
                        print(MAILMAN_CFG_TEMPLATE.format(
                            now().replace(microsecond=0)), file=fp)

    @property
    def runner_configs(self):
        """Iterate over all the runner configuration sections."""
        for section in self._config.getByCategory('runner', []):
            yield section

    @property
    def archivers(self):
        """Iterate over all the archivers."""
        for section in self._config.getByCategory('archiver', []):
            class_path = section['class'].strip()
            if len(class_path) == 0:
                continue
            archiver = call_name(class_path)
            archiver.is_enabled = as_boolean(section.enable)
            yield archiver

    @property
    def language_configs(self):
        """Iterate over all the language configuration sections."""
        for section in self._config.getByCategory('language', []):
            yield section



def load_external(path, encoding=None):
    """Load the configuration file named by path.

    :param path: A string naming the location of the external configuration
        file.  This is either an absolute file system path or a special
        ``python:`` path.  When path begins with ``python:``, the rest of the
        value must name a ``.cfg`` file located within Python's import path,
        however the trailing ``.cfg`` suffix is implied (don't provide it
        here).
    :param encoding: The encoding to apply to the data read from path.  If
        None, then bytes will be returned.
    :return: A unicode string or bytes, depending on ``encoding``.
    """
    # Is the context coming from a file system or Python path?
    if path.startswith('python:'):
        resource_path = path[7:]
        package, dot, resource = resource_path.rpartition('.')
        config_string = resource_string(package, resource + '.cfg')
    else:
        with open(path, 'rb') as fp:
            config_string = fp.read()
    if encoding is None:
        return config_string
    return config_string.decode(encoding)


def external_configuration(path):
    """Parse the configuration file named by path.

    :param path: A string naming the location of the external configuration
        file.  This is either an absolute file system path or a special
        ``python:`` path.  When path begins with ``python:``, the rest of the
        value must name a ``.cfg`` file located within Python's import path,
        however the trailing ``.cfg`` suffix is implied (don't provide it
        here).
    :return: A `ConfigParser` instance.
    """
    # Is the context coming from a file system or Python path?
    if path.startswith('python:'):
        resource_path = path[7:]
        package, dot, resource = resource_path.rpartition('.')
        cfg_path = resource_filename(package, resource + '.cfg')
    else:
        cfg_path = path
    parser = SafeConfigParser()
    files = parser.read(cfg_path)
    if files != [cfg_path]:
        raise MissingConfigurationFileError(path)
    return parser
