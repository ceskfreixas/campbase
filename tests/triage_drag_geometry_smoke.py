# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep Triage cells stable and insertion previews fully inside their destination."""
import copy
import tempfile
import time
from pathlib import Path
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Adw, Gdk, GLib, Gtk
from campbase.__main__ import demo_snapshot
from campbase.storage import Store
from campbase.window import Window
from campbase.widgets import Column
from campbase.workflow_sections import fold_column
from campbase.workflow_state import save_options


def settle(duration=.5):
    end=time.monotonic()+duration
    while time.monotonic()<end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        time.sleep(.005)


def descendants(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from descendants(child);child=child.get_next_sibling()


def column(window,key):
    return next(item for item in descendants(window.board_body) if isinstance(item,Column) and item.stack['id']==key)


app=Adw.Application(application_id='cat.ceskfreixas.Campbase.DragGeometryCheck');app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

def sizes(current):
    return [(tile.card['id'],tile.get_width(),tile.get_height()) for tile in current.drop.widgets if tile.get_mapped()]

def check_preview_bounds(drop):
    preview=drop.placeholder
    marker=next(item for item in descendants(preview) if item.has_css_class('drop-placeholder'))
    ok,bounds=marker.compute_bounds(preview)
    assert ok
    assert bounds.origin.x>=0 and bounds.origin.y>=0
    assert bounds.origin.x+bounds.size.width<=preview.get_width()+1
    assert bounds.origin.y+bounds.size.height<=preview.get_height()+1,(
        bounds.origin.y,bounds.size.height,preview.get_height())


def check_cell(current):
    expected=current.drop.cards_box.cell_width()
    assert all(abs(width-expected)<=1 for _,width,_ in sizes(current)),(expected,sizes(current))

with tempfile.TemporaryDirectory() as folder:
    store=Store(folder);store.set_setting('auto_sync',False)
    snapshot=demo_snapshot();sample=copy.deepcopy(snapshot['stacks']['1'][1]['cards'][0])
    incoming=dict(sample,id=4000,stackId=2,title='Targeta amb una descripció una mica més llarga',order=0,
        description='- [x] Primera tasca\n- [ ] Segona tasca',commentsCount=9,_textCommentsCount=2)
    snapshot['stacks']['1'][1]['cards']=[incoming]
    base=[dict(sample,id=5000+i,stackId=1,title=f'Tasca {i+1}',order=i,
              description='',commentsCount=0,labels=[]) for i in range(6)]
    snapshot['stacks']['1'][0]['cards']=base
    store.put('snapshot',snapshot);store.set_setting('columns_per_row',3)
    save_options(store,1,not_now_enabled=True,not_now_stack=2,not_now_expanded=False)
    w=Window(app,store,True);w.set_default_size(1200,1000);w.present();settle()
    for width in (943,1200):
        w.set_default_size(width,1000);settle()
        for expanded in (False,True):
            fold_column(column(w,2),expanded);settle()
            current=column(w,1);check_cell(current)
            before={key:width for key,width,_ in sizes(current)}
            source=column(w,2).drop.widgets[0]
            w.drag_session.begin(source,source.card);settle(.04)
            current.drop.motion(None,20,70);settle(.2)
            check_cell(current)
            marker=current.drop.placeholder
            check_preview_bounds(current.drop)
            assert marker is not None
            assert abs(marker.get_width()-current.drop.cards_box.cell_width())<=1
            heights=[height for _,_,height in sizes(current)]
            assert all(abs(marker.get_height()-height)<=1 for height in heights),(marker.get_height(),heights)
            assert all(abs(tile.get_width()-before[tile.card['id']])<=1 for tile in current.drop.widgets)
            current.drop.motion(None,current.get_width()-30,160);settle(.2)
            check_cell(current)
            w.drag_session.finish();settle()
            check_cell(current)
            assert all(abs(tile.get_width()-before[tile.card['id']])<=1 for tile in current.drop.widgets)
    # Reordering within Triage must not grow its rows just for the insertion
    # cue or the temporary pending status, including after server confirmation.
    current=column(w,1)
    original={key:(width,height) for key,width,height in sizes(current)}
    source=current.drop.widgets[0]
    w.drag_session.begin(source,source.card)
    x,y=current.get_width()-20,current.get_height()-20
    current.drop.motion(None,x,y);settle(.2)
    assert abs(current.drop.placeholder.get_height()-next(iter(original.values()))[1])<=1
    assert current.drop.drop(None,'campbase-card:'+str(source.card['id']),x,y)
    w.drag_session.finish();settle()
    assert {key:(width,height) for key,width,height in sizes(column(w,1))}==original
    operation=store.operations()[0]
    confirmed={key:value for key,value in w.find_card(source.card['id']).items() if not key.startswith('_')}
    store.complete(operation,confirmed);w.render();settle()
    assert {key:(width,height) for key,width,height in sizes(column(w,1))}==original
    # Real queued move followed by its simulated server acknowledgement must
    # preserve geometry, including when the pending clock and reply count change.
    current=column(w,1);source=column(w,2).drop.widgets[0]
    w.drag_session.begin(source,source.card);current.drop.motion(None,20,70);settle(.2)
    preview=(current.drop.placeholder.get_width(),current.drop.placeholder.get_height())
    assert current.drop.drop(None,'campbase-card:4000',20,70)
    w.drag_session.finish();settle()
    current=column(w,1);pending=sizes(current);check_cell(current)
    assert all(abs(height-preview[1])<=1 for _,_,height in pending),(preview,pending)
    operation=store.operations()[0]
    confirmed={key:value for key,value in w.find_card(4000).items() if not key.startswith('_')}
    confirmed['_textCommentsCount']=2
    store.complete(operation,confirmed);w.render();settle()
    assert sizes(column(w,1))==pending,(pending,sizes(column(w,1)))
    settle(.8)
    assert sizes(column(w,1))==pending
    # A late reply-filtered comment total must not steal title space and
    # change row heights after the drag has already finished.
    fresh=store.get('snapshot')
    moved=next(c for c in fresh['stacks']['1'][0]['cards'] if c['id']==4000)
    moved['_textCommentsCount']=None
    store.put('snapshot',fresh);w.render();settle()
    without_total=sizes(column(w,1))
    moved['_textCommentsCount']=2
    store.put('snapshot',fresh);w.render();settle()
    assert sizes(column(w,1))==without_total
    # The grid also keeps its cell unit with one card and an empty destination.
    for count in (1,0):
        fresh=store.get('snapshot');fresh['stacks']['1'][0]['cards']=base[:count]
        fresh['stacks']['1'][1]['cards']=[incoming];store.put('snapshot',fresh);w.render();settle()
        current=column(w,1);check_cell(current)
        source=column(w,2).drop.widgets[0]
        w.drag_session.begin(source,source.card);current.drop.motion(None,20,70);settle(.2)
        assert abs(current.drop.placeholder.get_width()-current.drop.cards_box.cell_width())<=1
        w.drag_session.finish();settle()
    # Without the deferred rail the same rule applies, including restoration
    # from an archived source whose inline folder icon disappears on arrival.
    fresh=store.get('snapshot');fresh['stacks']['1'][0]['cards']=base
    archived=dict(incoming,id=6000,stackId=3,archived=True,title='Arxivada amb un títol prou llarg per repartir-se en més d’una línia')
    fresh['stacks']['1'][2]['cards']=[archived];store.put('snapshot',fresh)
    save_options(store,1,not_now_enabled=False);w.render();settle()
    w.show_archived(3,True);settle()
    current=column(w,1);check_cell(current)
    source=column(w,3).archived_section.cards[0]
    w.drag_session.begin(source,source.card);current.drop.motion(None,20,70);settle(.2)
    preview=(current.drop.placeholder.get_width(),current.drop.placeholder.get_height())
    assert current.drop.drop(None,'campbase-card:6000',20,70)
    w.drag_session.finish();settle()
    current=column(w,1);check_cell(current)
    assert all(abs(height-preview[1])<=1 for _,_,height in sizes(current)),(preview,sizes(current))
    # An empty ordinary column must show the complete border too. Wrapping
    # the overlay label used to give it a taller minimum than its card model.
    fresh=store.get('snapshot')
    fresh['stacks']['1'][0]['cards']=[dict(id=7000,stackId=1,title='+Aixeta',order=0,archived=False,labels=[])]
    store.put('snapshot',fresh);w.render();settle()
    from campbase import i18n
    for language in ('ca','eu','gl','es','oc','en'):
        i18n.change_language(language);settle(.15)
        for target_id in (3,1):
            source=next(tile for tile in column(w,1).drop.widgets if tile.card['id']==7000)
            target=column(w,target_id)
            w.drag_session.begin(source,source.card)
            target.drop.motion(None,20,70);settle(.25)
            check_preview_bounds(target.drop)
            w.drag_session.finish();settle(.1)
    w.close()
print('PASS stable Triage cells, complete preview borders in six languages, destination sizing, sync acknowledgement and sparse lists')
