#-*- python -*-
import logging
from datetime import datetime

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, redirect, flash
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import g, c, request, response
from formencode import validators
from pymongo.bson import ObjectId
from webob import exc

# Pyforge-specific imports
from allura.app import Application, ConfigOption, SitemapEntry
from allura.lib import helpers as h
from allura.lib.search import search
from allura.lib.decorators import audit, react
from allura.lib.security import require, has_artifact_access
from allura.lib import widgets as w
from allura.lib.widgets.subscriptions import SubscribeForm
from allura.lib.widgets import form_fields as ffw
from allura import model as M
from allura.controllers import BaseController, AppDiscussionController

# Local imports
from forgeblog import model as BM
from forgeblog import version
from forgeblog import widgets

log = logging.getLogger(__name__)

class W:
    thread=w.Thread(
        page=None, limit=None, page_size=None, count=None,
        style='linear')
    new_post_form = widgets.NewPostForm()
    edit_post_form = widgets.EditPostForm()
    view_post_form = widgets.ViewPostForm()
    label_edit = ffw.LabelEdit()
    attachment_add = ffw.AttachmentAdd()
    attachment_list = ffw.AttachmentList()
    preview_post_form = widgets.PreviewPostForm()
    subscribe_form = SubscribeForm()

class ForgeBlogApp(Application):
    __version__ = version.__version__
    tool_label='Blog'
    default_mount_label='Blog'
    default_mount_point='blog'
    permissions = ['configure', 'read', 'write',
                    'unmoderated_post', 'post', 'moderate', 'admin']
    ordinal=13
    installable=True
    config_options = Application.config_options
    show_discussion=True

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()

    @audit('blog.#')
    def auditor(self, routing_key, data):
        log.info('Auditing data from %s (%s)',
                 routing_key, self.config.options.mount_point)

    @react('blog.#')
    def reactor(self, routing_key, data):
        log.info('Reacting to data from %s (%s)',
                 routing_key, self.config.options.mount_point)

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label.title()
        with h.push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    @h.exceptionless([], log)
    def sidebar_menu(self):
        base = c.app.url
        links = [
            SitemapEntry('Home', base),
            SitemapEntry('Search', base + 'search'),
            ]
        if has_artifact_access('write')():
            links += [ SitemapEntry('New Post', base + 'new') ]
        return links

    def admin_menu(self):
        admin_url = c.project.url()+'admin/'+self.config.options.mount_point+'/'
        links = [
            SitemapEntry('Permissions',
                         admin_url + 'permissions/',
                         className='nav_child'),
            ]
        return links

    @property
    def templates(self):
         return pkg_resources.resource_filename('forgeblog', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'
        super(ForgeBlogApp, self).install(project)

        # Setup permissions
        role_developer = M.ProjectRole.query.get(name='Developer')._id
        role_auth = M.ProjectRole.query.get(name='*authenticated')._id
        role_anon = M.ProjectRole.query.get(name='*anonymous')._id
        self.config.acl.update(
            configure=c.project.acl['tool'],
            read=c.project.acl['read'],
            write=[role_developer],
            unmoderated_post=[role_auth],
            post=[role_anon],
            moderate=[role_developer],
            admin=c.project.acl['tool'])

    def uninstall(self, project):
        "Remove all the tool's artifacts from the database"
        BM.Attachment.query.remove({'metadata.app_config_id':c.app.config._id})
        BM.BlogPost.query.remove(dict(app_config_id=c.app.config._id))
        BM.BlogPostSnapshot.query.remove(dict(app_config_id=c.app.config._id))
        super(ForgeBlogApp, self).uninstall(project)

class RootController(BaseController):

    def __init__(self):
        setattr(self, 'feed.atom', self.feed)
        setattr(self, 'feed.rss', self.feed)
        self._discuss = AppDiscussionController()

    @expose('forgeblog.templates.index')
    @with_trailing_slash
    def index(self, **kw):
        if has_artifact_access('write', None)():
            posts = BM.BlogPost.query.find(dict(
                    app_config_id=c.app.config._id)).sort('-timestamp')
        else:
            posts = BM.BlogPost.query.find(dict(
                        state='published',
                        app_config_id=c.app.config._id)).sort('-timestamp')
        c.form = W.preview_post_form
        return dict(posts=posts)

    @expose('forgeblog.templates.search')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False)))
    def search(self, q=None, history=None):
        'local tool search'
        results = []
        count=0
        if not q:
            q = ''
        else:
            results = search(
                q,
                fq=[
                    'is_history_b:%s' % history,
                    'project_id_s:%s' % c.project._id,
                    'mount_point_s:%s'% c.app.config.options.mount_point ])
            if results: count=results.hits
        return dict(q=q, history=history, results=results or [], count=count)

    @expose('forgeblog.templates.edit_post')
    @without_trailing_slash
    def new(self, **kw):
        require(has_artifact_access('write', None))
        now = datetime.utcnow()
        post = dict(
            title='Please enter a title',
            text='Type your text here',
            date=now.date(),
            time=now.time(),
            state='draft')
        c.form = W.new_post_form
        return dict(post=post)

    @expose()
    @validate(form=W.edit_post_form, error_handler=new)
    @without_trailing_slash
    def save(self, **kw):
        require(has_artifact_access('write', None))
        post = BM.BlogPost()
        for k,v in kw.iteritems():
            setattr(post, k, v)
        post.make_slug()
        post.commit()
        M.Thread(discussion_id=post.app_config.discussion_id,
               artifact_reference=post.dump_ref(),
               subject='%s discussion' % post.title)
        redirect(post.url())


    @without_trailing_slash
    @expose()
    @validate(dict(
            since=h.DateTimeConverter(if_empty=None, if_invalid=None),
            until=h.DateTimeConverter(if_empty=None, if_invalid=None),
            offset=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, offset=None, limit=None):
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        title = 'Recent changes to %s' % c.app.config.options.mount_point
        feed = M.Feed.feed(
            {'artifact_reference.mount_point':c.app.config.options.mount_point,
             'artifact_reference.project_id':c.project._id},
            feed_type,
            title,
            c.app.url,
            title,
            since, until, offset, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')
    @expose()
    def _lookup(self, year, month, name, *rest):
        slug = '/'.join((year, month, name))
        post = BM.BlogPost.query.get(slug=slug)
        if post is None:
            raise exc.HTTPNotFound()
        return PostController(post), rest

class PostController(BaseController):

    def __init__(self, post):
        self.post = post
        setattr(self, 'feed.atom', self.feed)
        setattr(self, 'feed.rss', self.feed)

    @expose('forgeblog.templates.post')
    @with_trailing_slash
    def index(self, **kw):
        c.form = W.view_post_form
        c.subscribe_form = W.subscribe_form
        c.thread = W.thread
        version = kw.pop('version', None)
        post = self._get_version(version)
        return dict(post=post)

    @expose('forgeblog.templates.edit_post')
    @without_trailing_slash
    def edit(self, **kw):
        require(has_artifact_access('write', None))
        c.form = W.edit_post_form
        c.attachment_add = W.attachment_add
        c.attachment_list = W.attachment_list
        c.label_edit = W.label_edit
        return dict(post=self.post)

    @without_trailing_slash
    @expose('forgeblog.templates.post_history')
    def history(self):
        require(has_artifact_access('read', self.post))
        posts = self.post.history()
        return dict(title=self.post.title, posts=posts)

    @without_trailing_slash
    @expose('forgeblog.templates.post_diff')
    def diff(self, v1, v2):
        require(has_artifact_access('read', self.post))
        p1 = self._get_version(int(v1))
        p2 = self._get_version(int(v2))
        result = h.diff_text(p1.text, p2.text)
        return dict(p1=p1, p2=p2, edits=result)

    @expose()
    @validate(form=W.edit_post_form, error_handler=edit)
    @without_trailing_slash
    def save(self, delete=None, **kw):
        require(has_artifact_access('write', None))
        if delete:
            self.post.delete()
            flash('Post deleted')
            redirect(c.app.url)
        for k,v in kw.iteritems():
            setattr(self.post, k, v)
        self.post.commit()
        redirect('.')

    @without_trailing_slash
    @expose()
    def revert(self, version):
        require(has_artifact_access('write', self.post))
        orig = self._get_version(version)
        if orig:
            self.post.text = orig.text
        self.post.commit()
        redirect('.')

    @expose()
    @validate(W.subscribe_form)
    def subscribe(self, subscribe=None, unsubscribe=None):
        require(has_artifact_access('read'))
        if subscribe:
            self.post.subscribe(type='direct')
        elif unsubscribe:
            self.post.unsubscribe()
        redirect(request.referer)

    @without_trailing_slash
    @expose()
    @validate(dict(
            since=h.DateTimeConverter(if_empty=None, if_invalid=None),
            until=h.DateTimeConverter(if_empty=None, if_invalid=None),
            offset=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, offset=None, limit=None):
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        feed = M.Feed.feed(
            {'artifact_reference':self.post.dump_ref()},
            feed_type,
            'Recent changes to %s' % self.post.title,
            self.post.url(),
            'Recent changes to %s' % self.post.title,
            since, until, offset, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')

    def _get_version(self, version):
        if not version: return self.post
        try:
            return self.post.get_version(version)
        except ValueError:
            return None