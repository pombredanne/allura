import ew
from allura.lib.widgets import form_fields as ffw

class HgLog(ew.Widget):
    template='jinja:hg_widgets/log.html'
    params=['value', 'limit', 'page', 'count', 'show_paging', 'fields']
    value=None
    limit=None
    page=0
    count=0
    show_paging=True

    class fields(ew.WidgetsList):
        page_list=ffw.PageList()
        page_size=ffw.PageSize()