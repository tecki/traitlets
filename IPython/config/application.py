# encoding: utf-8
"""
A base class for a configurable application.

Authors:

* Brian Granger
"""

#-----------------------------------------------------------------------------
#  Copyright (C) 2008-2011  The IPython Development Team
#
#  Distributed under the terms of the BSD License.  The full license is in
#  the file COPYING, distributed as part of this software.
#-----------------------------------------------------------------------------

#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------

from copy import deepcopy
import logging
import sys

from IPython.config.configurable import SingletonConfigurable
from IPython.config.loader import (
    KeyValueConfigLoader, PyFileConfigLoader, Config
)

from IPython.utils.traitlets import (
    Unicode, List, Int, Enum, Dict
)
from IPython.utils.text import indent

#-----------------------------------------------------------------------------
# Descriptions for the various sections
#-----------------------------------------------------------------------------

flag_description = """
Flags are command-line arguments passed as '--<flag>'.
These take no parameters, unlike regular key-value arguments.
They are typically used for setting boolean flags, or enabling
modes that involve setting multiple options together.
""".strip() # trim newlines of front and back

alias_description = """
These are commonly set parameters, given abbreviated aliases for convenience.
They are set in the same `name=value` way as class parameters, where
<name> is replaced by the real parameter for which it is an alias.
""".strip() # trim newlines of front and back

keyvalue_description = """
Parameters are set from command-line arguments of the form:
`Class.trait=value`.  Parameters will *never* be prefixed with '-'.
This line is evaluated in Python, so simple expressions are allowed, e.g.
    `C.a='range(3)'`   For setting C.a=[0,1,2]
""".strip() # trim newlines of front and back

#-----------------------------------------------------------------------------
# Application class
#-----------------------------------------------------------------------------


class ApplicationError(Exception):
    pass


class Application(SingletonConfigurable):
    """A singleton application with full configuration support."""

    # The name of the application, will usually match the name of the command
    # line application
    name = Unicode(u'application')

    # The description of the application that is printed at the beginning
    # of the help.
    description = Unicode(u'This is an application.')
    # default section descriptions
    flag_description = Unicode(flag_description)
    alias_description = Unicode(alias_description)
    keyvalue_description = Unicode(keyvalue_description)
    

    # A sequence of Configurable subclasses whose config=True attributes will
    # be exposed at the command line.
    classes = List([])

    # The version string of this application.
    version = Unicode(u'0.0')

    # The log level for the application
    log_level = Enum((0,10,20,30,40,50), default_value=logging.WARN,
                     config=True,
                     help="Set the log level.")
    
    # the alias map for configurables
    aliases = Dict(dict(log_level='Application.log_level'))
    
    # flags for loading Configurables or store_const style flags
    # flags are loaded from this dict by '--key' flags
    # this must be a dict of two-tuples, the first element being the Config/dict
    # and the second being the help string for the flag
    flags = Dict()
    

    def __init__(self, **kwargs):
        SingletonConfigurable.__init__(self, **kwargs)
        # Add my class to self.classes so my attributes appear in command line
        # options.
        self.classes.insert(0, self.__class__)
        
        # ensure self.flags dict is valid
        for key,value in self.flags.iteritems():
            assert len(value) == 2, "Bad flag: %r:%s"%(key,value)
            assert isinstance(value[0], (dict, Config)), "Bad flag: %r:%s"%(key,value)
            assert isinstance(value[1], basestring), "Bad flag: %r:%s"%(key,value)
        self.init_logging()

    def _config_changed(self, name, old, new):
        SingletonConfigurable._config_changed(self, name, old, new)
        self.log.debug('Config changed:')
        self.log.debug(repr(new))

    def init_logging(self):
        """Start logging for this application.

        The default is to log to stdout using a StreaHandler. The log level
        starts at loggin.WARN, but this can be adjusted by setting the 
        ``log_level`` attribute.
        """
        self.log = logging.getLogger(self.__class__.__name__)
        self.log.setLevel(self.log_level)
        self._log_handler = logging.StreamHandler()
        self._log_formatter = logging.Formatter("[%(name)s] %(message)s")
        self._log_handler.setFormatter(self._log_formatter)
        self.log.addHandler(self._log_handler)

    def _log_level_changed(self, name, old, new):
        """Adjust the log level when log_level is set."""
        self.log.setLevel(new)
    
    def print_alias_help(self):
        """print the alias part of the help"""
        if not self.aliases:
            return
        
        lines = ['Aliases']
        lines.append('_'*len(lines[0]))
        lines.append(self.alias_description)
        lines.append('')
        
        classdict = {}
        for c in self.classes:
            classdict[c.__name__] = c
        
        for alias, longname in self.aliases.iteritems():
            classname, traitname = longname.split('.',1)
            cls = classdict[classname]
            
            trait = cls.class_traits(config=True)[traitname]
            help = cls.class_get_trait_help(trait)
            help = help.replace(longname, "%s (%s)"%(alias, longname), 1)
            lines.append(help)
            # header = "%s (%s) : %s"%(alias, longname, trait.__class__.__name__)
            # lines.append(header)
            # help = cls.class_get_trait_help(trait)
            # if help:
            #     lines.append(indent(help, flatten=True))
        lines.append('')
        print '\n'.join(lines)
    
    def print_flag_help(self):
        """print the flag part of the help"""
        if not self.flags:
            return
        
        lines = ['Flags']
        lines.append('_'*len(lines[0]))
        lines.append(self.flag_description)
        lines.append('')
        
        for m, (cfg,help) in self.flags.iteritems():
            lines.append('--'+m)
            lines.append(indent(help, flatten=True))
        lines.append('')
        print '\n'.join(lines)
    
    def print_help(self, classes=False):
        """Print the help for each Configurable class in self.classes.
        
        If classes=False (the default), only flags and aliases are printed
        """
        self.print_flag_help()
        self.print_alias_help()
        
        if classes:
            if self.classes:
                print "Class parameters"
                print "----------------"
                print self.keyvalue_description
                print
        
            for cls in self.classes:
                cls.class_print_help()
                print
        else:
            print "To see all available configurables, use `--help-all`"
            print

    def print_description(self):
        """Print the application description."""
        print self.description
        print

    def print_version(self):
        """Print the version string."""
        print self.version

    def update_config(self, config):
        """Fire the traits events when the config is updated."""
        # Save a copy of the current config.
        newconfig = deepcopy(self.config)
        # Merge the new config into the current one.
        newconfig._merge(config)
        # Save the combined config as self.config, which triggers the traits
        # events.
        self.config = newconfig

    def parse_command_line(self, argv=None):
        """Parse the command line arguments."""
        argv = sys.argv[1:] if argv is None else argv

        if '-h' in argv or '--help' in argv or '--help-all' in argv:
            self.print_description()
            self.print_help('--help-all' in argv)
            self.exit(0)

        if '--version' in argv:
            self.print_version()
            self.exit(0)
        
        loader = KeyValueConfigLoader(argv=argv, aliases=self.aliases,
                                        flags=self.flags)
        config = loader.load_config()
        self.update_config(config)

    def load_config_file(self, filename, path=None):
        """Load a .py based config file by filename and path."""
        loader = PyFileConfigLoader(filename, path=path)
        config = loader.load_config()
        self.update_config(config)

    def exit(self, exit_status=0):
        self.log.debug("Exiting application: %s" % self.name)
        sys.exit(exit_status)

#-----------------------------------------------------------------------------
# utility functions, for convenience
#-----------------------------------------------------------------------------

def boolean_flag(name, configurable, set_help='', unset_help=''):
    """helper for building basic --trait, --no-trait flags
    
    Parameters
    ----------
    
    name : str
        The name of the flag.
    configurable : str
        The 'Class.trait' string of the trait to be set/unset with the flag
    set_help : unicode
        help string for --name flag
    unset_help : unicode
        help string for --no-name flag
    
    Returns
    -------
    
    cfg : dict
        A dict with two keys: 'name', and 'no-name', for setting and unsetting
        the trait, respectively.
    """
    # default helpstrings
    set_help = set_help or "set %s=True"%configurable
    unset_help = unset_help or "set %s=False"%configurable
    
    cls,trait = configurable.split('.')
    
    setter = Config()
    setter[cls][trait] = True
    unsetter = Config()
    unsetter[cls][trait] = False
    return {name : (setter, set_help), 'no-'+name : (unsetter, unset_help)}
