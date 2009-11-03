# -*- coding: iso-8859-1 -*-
"""
run_server
==========

:Author: Ho Chun Wei, fuzzybr80(at)gmail.com (author of original PyFileServer)
:Author: Martin Wendt, moogle(at)wwwendt.de 
:Copyright: Lesser GNU Public License, see LICENSE file attached with package

Standalone server that runs WsgiDAV.

These tasks are performed:

    - Set up the configuration from defaults, configuration file, and command line
      options.
    - Instantiate the WsgiDAVApp object (which is a WSGI application)
    - Start a WSGI server for this WsgiDAVApp object   

Configuration is defined like this:

    1. Get the name of a configuration file from command line option
       ``--config-file=FILENAME`` (or short ``-cFILENAME``).
       If this option is omitted, we use ``wsgidav.conf`` in the current 
       directory.
    2. Set reasonable default settings. 
    3. If configuration file exists: read and use it to overwrite defaults.
    4. If command line options are passed, use them to override settings:
    
       ``--host`` option overrides ``hostname`` setting.
         
       ``--port`` option overrides ``port`` setting.  
       
       ``--root=FOLDER`` option creates a FilesystemProvider that publishes 
       FOLDER on the '/' share.

See DEVELOPERS.txt_ for more information about the WsgiDAV architecture.

.. _DEVELOPERS.txt: http://wiki.wsgidav-dev.googlecode.com/hg/DEVELOPERS.html  
"""
from optparse import OptionParser
from pprint import pprint
from inspect import isfunction
import traceback
import sys
import os
try:
    from wsgidav.version import __version__
    from wsgidav.wsgidav_app import WsgiDAVApp
    from wsgidav.fs_dav_provider import FilesystemProvider
except ImportError, e:
    raise RuntimeError("Could not import wsgidav package:\n%s\nSee http://wsgidav.googlecode.com/." % e)

__docformat__ = "reStructuredText"

# Use this config file, if no --config_file option is specified
DEFAULT_CONFIG_FILE = "wsgidav.conf"

# Use these settings, if config file does not define them (or is totally missing)  
DEFAULT_CONFIG = {
    "provider_mapping": {},
    "user_mapping": {},
#    "host": "127.0.0.1",
#    "port": 80, 
    "propsmanager": None,                    
    "propsfile": None, 
    "locksmanager": None,  # None: use lock_manager.LockManager                   
    "locksfile": None, # Used as default for 
    "domaincontroller": None,

    # HTTP Authentication Options
    "acceptbasic": True,    # Allow basic authentication, True or False
    "acceptdigest": True,   # Allow digest authentication, True or False
    "defaultdigest": True,  # True (default digest) or False (default basic)
    
    # Verbose Output
    "verbose": 2,        # 0 - no output (excepting application exceptions)         
                         # 1 - show single line request summaries (for HTTP logging)
                         # 2 - show additional events
                         # 3 - show full request/response header info (HTTP Logging)
                         #     request body and GET response bodies not shown
    
    
    # Organizational Information - printed as a footer on html output
    "response_trailer": None,
}



def _initCommandLineOptions():
    """Parse command line options into a dictionary."""
    
    usage = """\
%prog [options]

Examples:
Share filesystem folder '/temp': 
  wsgidav --port=80 --host=0.0.0.0 --root=/temp
Run using a configuration file: 
  wsgidav --port=80 --host=0.0.0.0 --config=~/wsgidav.conf

If no config file is specified, the application will look for a file named
'wsgidav.conf' in the current directory.
See sample_wsgidav.conf for some explanation of the configuration file format.
If no config file is found, a default FilesystemProvider is used."""

#    description = """\
#%prog is a standalone server for WsgiDAV.
#It tries to use pre-installed WSGI servers (cherrypy.wsgiserver,
#paste.httpserver, wsgiref.simple_server) or uses our built-in
#ext_wsgiutils_server.py."""

    epilog = """Licensed under LGPL.
See http://wsgidav.googlecode.com for additional information."""
            
    parser = OptionParser(usage=usage, 
                          version=__version__,
#                          conflict_handler="error",
                          description=None, #description,
                          add_help_option=True,
#                          prog="wsgidav",
                          epilog=epilog
                          )    
 
    parser.add_option("-p", "--port", 
                      dest="port",
                      type="int",
                      default=8080,
                      help='port to serve on (default: %default)')
    parser.add_option("-H", "--host", # '-h' conflicts with --help  
                      dest="host",
                      default="localhost",
                      help="host to serve from (default: %default). 'localhost' is only accessible from the local computer. Use 0.0.0.0 to make your application public"),
    parser.add_option("-r", "--root",
                      dest="root_path", 
                      help="Path to a file system folder to publish as share '/'.")

    parser.add_option("-q", "--quiet",
                      action="store_const", const=0, dest="verbose",
                      help="suppress any output except for errors.")
    parser.add_option("-v", "--verbose",
                      action="store_const", const=2, dest="verbose", default=1,
                      help="Set verbose = 2: print informational output.")
    parser.add_option("-d", "--debug",
                      action="store_const", const=3, dest="verbose",
                      help="Set verbose = 3: print requests and responses.")
    
    parser.add_option("-c", "--config",
                      dest="config_file", 
                      help="Configuration file (default: %default).")

   
    (options, args) = parser.parse_args()

    if len(args) > 0:
        parser.error("Too many arguments")

    if options.config_file is None:
        # If --config was omitted, use default (if it exists)
        defPath = os.path.abspath(DEFAULT_CONFIG_FILE)
        if os.path.exists(defPath):
            if options.verbose >= 2:
                print "Using default config file: %s" % defPath
            options.config_file = defPath
    else:
        # If --config was specified convert to absolute path and assert it exists
        options.config_file = os.path.abspath(options.config_file)
        if not os.path.exists(options.config_file):
            parser.error("Invalid config file specified: %s" % options.config_file)

    # Convert options object to dictionary
    cmdLineOpts = options.__dict__.copy()
    if options.verbose >= 3:
        print "Command line options:"
        for k, v in cmdLineOpts.items():
            print "    %-12s: %s" % (k, v)
    return cmdLineOpts




def _readConfigFile(config_file, verbose):
    """Read configuration file options into a dictionary."""

    if not os.path.exists(config_file):
        raise RuntimeError("Couldn't open configuration file '%s'." % config_file)
    
    try:
        import imp
        conf = {}
        configmodule = imp.load_source("configuration_module", config_file)

        for k, v in vars(configmodule).items():
            if k.startswith("__"):
                continue
            elif isfunction(v):
                continue
            conf[k] = v               
    except Exception, e:
        if verbose >= 1:
            traceback.print_exc() 
        exceptioninfo = traceback.format_exception_only(sys.exc_type, sys.exc_value) #@UndefinedVariable
        exceptiontext = ''
        for einfo in exceptioninfo:
            exceptiontext += einfo + '\n'   
        raise RuntimeError("Failed to read configuration file: " + config_file + "\nDue to " + exceptiontext)
    
    return conf




def _initConfig():
    """Setup configuration dictionary from default, command line and configuration file."""
    cmdLineOpts = _initCommandLineOptions()

    # Set config defaults
    config = DEFAULT_CONFIG.copy()

    # Configuration file overrides defaults
    config_file = cmdLineOpts.get("config_file")
    if config_file: 
        verbose = cmdLineOpts.get("verbose", 2)
        fileConf = _readConfigFile(config_file, verbose)
        config.update(fileConf)
    else:
        if cmdLineOpts["verbose"] >= 2:
            print "Running without configuration file."
    
    # Command line overrides file
    if cmdLineOpts.get("port"):
        config["port"] = cmdLineOpts.get("port")
    if cmdLineOpts.get("host"):
        config["host"] = cmdLineOpts.get("host")
    if cmdLineOpts.get("verbose"):
        config["verbose"] = cmdLineOpts.get("verbose")

    if cmdLineOpts.get("root_path"):
        config["provider_mapping"]["/"] = FilesystemProvider(cmdLineOpts.get("root_path"))
    
    if cmdLineOpts["verbose"] >= 3:
        print "Configuration(%s):" % cmdLineOpts["config_file"]
        pprint(config)

    if not config["provider_mapping"]:
        print >>sys.stderr, "ERROR: No DAV provider defined. Try --help option."
        sys.exit(-1)
#        raise RuntimeWarning("No At least one DAV provider must be specified by a --root option, or in a configuration file.")
    return config




def _runPaste(app, config):
    """Run WsgiDAV using paste.httpserver, if Paste is installed.
    
    See http://pythonpaste.org/modules/httpserver.html for more options
    """
    try:
        from paste import httpserver
        if config["verbose"] >= 2:
            print "Running paste.httpserver..."
        # See http://pythonpaste.org/modules/httpserver.html for more options
        httpserver.serve(app, 
                         host=config["host"], 
                         port=config["port"],
                         server_version="WsgiDAV/%s" % __version__,
                         )
        # TODO: is this better? 
        #httpserver.server_runner(app, serverOpts)
    except ImportError, e:
        if config["verbose"] >= 2:
            print "Could not import paste.httpserver."
        return False
    return True




def _runCherryPy(app, config):
    """Run WsgiDAV using cherrypy.wsgiserver, if CherryPy is installed."""
    try:
        # http://cherrypy.org/apidocs/3.0.2/cherrypy.wsgiserver-module.html  
        from cherrypy import wsgiserver
        if config["verbose"] >= 2:
            print "wsgiserver.CherryPyWSGIServer..."
        server = wsgiserver.CherryPyWSGIServer(
            (config["host"], config["port"]), 
            app,
            server_name="WsgiDAV/%s" % __version__)
        server.start()
    except ImportError, e:
        if config["verbose"] >= 1:
            print "Could not import wsgiserver.CherryPyWSGIServer."
        return False
    return True




def _runSimpleServer(app, config):
    """Run WsgiDAV using wsgiref.simple_server, on Python 2.5+."""
    try:
        # http://www.python.org/doc/2.5.2/lib/module-wsgiref.html
        from wsgiref.simple_server import make_server
        if config["verbose"] >= 2:
            print "Running wsgiref.simple_server (single threaded)..."
        httpd = make_server(config["host"], config["port"], app)
#        print "Serving HTTP on port 8000..."
        httpd.serve_forever()
    except ImportError, e:
        if config["verbose"] >= 1:
            print "Could not import wsgiref.simple_server (part of standard lib since Python 2.5)."
        return False
    return True




def _runBuiltIn(app, config):
    """Run WsgiDAV using ext_wsgiutils_server from the WsgiDAV package."""
    try:
        import ext_wsgiutils_server
        if config["verbose"] >= 2:
            print "Running wsgidav.ext_wsgiutils_server..."
        ext_wsgiutils_server.serve(config, app)
    except ImportError, e:
        if config["verbose"] >= 1:
            print "Could not import wsgidav.ext_wsgiutils_server (part of WsgiDAV)."
        return False
    return True




def run():    
    config = _initConfig()
    
    
#    from paste import pyconfig
#    config = pyconfig.Config()
#    config.load(opts.config_file)

#    from paste.deploy import loadapp
#    app = loadapp('config:/path/to/config.ini')
#    app = loadapp("config:wsgidav.conf")

    app = WsgiDAVApp(config)
    
#    from wsgidav.wsgiapp import make_app
#    global_conf = {}
#    app = make_app(global_conf)

    res = False

#    if not res:
#        res = _runCherryPy(app, config) 

#    if not res:
#        res = _runPaste(app, config)

    # wsgiref.simple_server is single threaded 
#    if not res:
#        res = _runSimpleServer(app, config)

    if not res:
        res = _runBuiltIn(app, config)
    
    if not res:
        print "No supported WSGI server installed."   
    
if __name__ == "__main__":
    run()