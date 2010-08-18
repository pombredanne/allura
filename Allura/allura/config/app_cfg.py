# -*- coding: utf-8 -*-
"""
Global configuration file for TG2-specific settings in allura.

This file complements development/deployment.ini.

Please note that **all the argument values are strings**. If you want to
convert them into boolean, for example, you should use the
:func:`paste.deploy.converters.asbool` function, as in::
    
    from paste.deploy.converters import asbool
    setting = asbool(global_conf.get('the_setting'))
 
"""

from tg.configuration import AppConfig, config
from pylons.middleware import StatusCodeRedirect
from paste.deploy.converters import asbool
from routes import Mapper

import sfx.middleware
import allura
import allura.lib.helpers as h
from allura import model
from allura.lib import app_globals, custom_middleware

class ForgeConfig(AppConfig):

    def __init__(self, root_controller='root'):
        AppConfig.__init__(self)
        self.root_controller = root_controller
        self.package = allura
        self.renderers = [ 'json', 'genshi', 'mako' ]
        self.default_renderer = 'genshi'
        self.use_sqlalchemy = False
        self.use_toscawidgets = True
        self.use_transaction_manager = False
        # self.handle_status_codes = [ 403, 404 ]
        self.handle_status_codes = [ 403, 404 ]

    def add_error_middleware(self, global_conf, app):
        app = AppConfig.add_error_middleware(self, global_conf, app)
        app = custom_middleware.LoginRedirectMiddleware(app)
        return app

    def after_init_config(self):
        config['pylons.strict_c'] = True

    def add_core_middleware(self, app):
        if asbool(config.get('auth.method', 'local')=='sfx'):
            d = h.config_with_prefix(config, 'auth.')
            d.update(h.config_with_prefix(config, 'sfx.'))
            app = sfx.middleware.SfxMiddleware(app, d)
        return super(ForgeConfig, self).add_core_middleware(app)

    def setup_routes(self):
        map = Mapper(directory=config['pylons.paths']['controllers'],
                     always_scan=config['debug'])
        # Setup a default route for the root of object dispatch
        map.connect('*url', controller=self.root_controller,
                    action='routes_placeholder')
        config['routes.map'] = map

base_config = ForgeConfig()