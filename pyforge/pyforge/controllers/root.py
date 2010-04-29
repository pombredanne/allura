# -*- coding: utf-8 -*-
"""Main Controller"""
import logging, string, os
from collections import defaultdict

import pkg_resources
from tg import expose, flash, redirect, session, config, response, request
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import c, g

import ew
import ming

import pyforge
from pyforge.app import SitemapEntry
from pyforge.lib.base import BaseController, environ
from pyforge.lib import helpers as h
from pyforge.controllers.error import ErrorController
from pyforge import model as M
from pyforge.lib.widgets import project_list as plw
from .auth import AuthController
from .search import SearchController, ProjectBrowseController
from .static import StaticController
from .project import NeighborhoodController, HostNeighborhoodController
from .oembed import OEmbedController
from .rest import RestController

__all__ = ['RootController']

log = logging.getLogger(__name__)

class W:
    project_summary = plw.ProjectSummary()

class RootController(BaseController):
    """
    The root controller for the pyforge application.
    
    All the other controllers and WSGI applications should be mounted on this
    controller. For example::
    
        panel = ControlPanelController()
        another_app = AnotherWSGIApplication()
    
    Keep in mind that WSGI applications shouldn't be mounted directly: They
    must be wrapped around with :class:`tg.controllers.WSGIAppController`.
    
    """
    
    auth = AuthController()
    error = ErrorController()
    static = StaticController()
    search = SearchController()
    rest = RestController()

    def __init__(self):
        for n in M.Neighborhood.query.find():
            if n.url_prefix.startswith('//'): continue
            n.bind_controller(self)
        self.browse = ProjectBrowseController()

    @property
    def _ew_resources(self):
        return ew.ResourceManager.get()

    def _setup_request(self):
        uid = session.get('userid', None)
        c.project = c.app = None
        c.user = M.User.query.get(_id=uid) or M.User.anonymous()
        c.queued_messages = []

    def _cleanup_iterator(self, result):
        for x in result:
            yield x
        self._cleanup_request()

    def _cleanup_request(self):
        ming.orm.ormsession.ThreadLocalORMSession.flush_all()
        for msg in environ.get('allura.queued_messages', []):
            g._publish(**msg)
        ming.orm.ormsession.ThreadLocalORMSession.close_all()

    @expose('pyforge.templates.project_list')
    @with_trailing_slash
    def index(self):
        """Handle the front-page."""
        c.project_summary = W.project_summary
        psort = [(n, M.Project.query.find(dict(is_root=True, neighborhood_id=n._id, deleted=False)).sort('shortname').all())
                 for n in M.Neighborhood.query.find().sort('name')]
        categories = M.ProjectCategory.query.find({'parent_id':None}).sort('name').all()
        c.custom_sidebar_menu = [SitemapEntry('Categories')] + [
            SitemapEntry(cat.label, '/browse/'+cat.name, className='nav_child') for cat in categories
        ]
        return dict(projects=psort,title="All Projects",text=None)

    @expose()
    @without_trailing_slash
    def markdown_to_html(self, markdown, project=None, app=None):
        """Convert markdown to html."""
        if project:
            g.set_project(project)
            if app:
                g.set_app(app)
        html = g.markdown.convert(markdown)
        return html

    @expose()
    @without_trailing_slash
    def site_style(self):
        """Display the css for the default theme."""
        theme = M.Theme.query.find(dict(name='forge_default')).first()
        colors = dict(color1=theme.color1,
                      color2=theme.color2,
                      color3=theme.color3,
                      color4=theme.color4,
                      color5=theme.color5,
                      color6=theme.color6)
        tpl_fn = pkg_resources.resource_filename(
            'pyforge', 'templates/style.css')
        css = h.render_genshi_plaintext(tpl_fn,**colors)
        response.headers['Content-Type'] = ''
        response.content_type = 'text/css'
        return css
