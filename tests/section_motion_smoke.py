# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional Deck-backed workflow, native layout, drag routing and undo."""
import tempfile
import time
from pathlib import Path
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Adw, Gtk, Gdk, GLib
from campbase.storage import Store
from campbase.window import Window
from campbase.widgets import Column
from campbase.workflow_dialog import WorkflowDialog, toggle_hold_column
from campbase.workflow_state import options, save_options
from campbase.card_dialog import CardDialog
from campbase.card_sections import CardSection
from campbase.collaboration import remember_creator
from campbase.label_management import LabelManagerDialog, LabelEditDialog
from campbase.labels import NewLabelDialog
from campbase.triage_layout import TriageRow
from gui_helpers import wait_presented, wait_until


def settle():
    end=time.monotonic()+.5
    while time.monotonic()<end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        time.sleep(.005)


def descendants(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from descendants(child)
        child=child.get_next_sibling()


def column(window,key):
    return next(item for item in descendants(window.board_body) if isinstance(item,Column) and item.stack['id']==key)


app=Adw.Application(application_id='cat.ceskfreixas.Campbase.SectionMotionCheck');app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

def pump(duration=.4):
    end=time.monotonic()+duration
    while time.monotonic()<end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        time.sleep(.005)

with tempfile.TemporaryDirectory() as folder:
    store=Store(folder);store.set_setting('auto_sync',False)
    held={'id':9,'title':'On hold','color':'E9AD0C'}
    card={'id':99,'stackId':20,'boardId':1,'title':'Active example','description':'','order':0,'archived':False,'labels':[]}
    cards=[card,dict(card,id=100,labels=[held],title='Paused example')]
    cards += [dict(card,id=200+i,title=f'Archived {i}',archived=True,order=i) for i in range(4)]
    store.put('snapshot',{'boards':[{'id':1,'title':'Section example','labels':[held],
        'permissions':{'PERMISSION_EDIT':True,'PERMISSION_MANAGE':True}}],
        'stacks':{'1':[{'id':10,'title':'Triage','cards':[]},{'id':20,'title':'In progress','cards':cards}]}})
    save_options(store,1,hold_label=9,hold_enabled=True,hold_columns=[])
    w=Window(app,store,True);w.set_default_size(1100,950);w.present();pump()
    current=column(w,20)
    w.show_archived(20,True);pump(.06)
    section=current.archived_section
    assert section is not None and column(w,20) is current
    assert 0<section.revealer.get_height()<section.get_height(),(section.revealer.get_height(),section.get_height())
    pump();full=section.revealer.get_height()
    body_height=section.body_revealer.get_height()
    section.toggle();pump(.06)
    assert section.body.get_visible() and body_height/2<section.body_revealer.get_height()<body_height
    valid,body_bounds=section.body.compute_bounds(section.body_revealer)
    assert valid and 0<=body_bounds.origin.y<=10,body_bounds.origin.y
    pump();assert not section.body.get_visible()
    section.toggle();pump();assert section.body.get_visible()
    w.show_archived(20,False);pump(.06)
    assert current.archived_section is None and section.revealer.get_parent() is current.body
    assert 0<section.revealer.get_height()<full
    valid,section_bounds=section.compute_bounds(section.revealer)
    assert valid and section_bounds.origin.y>=0,section_bounds.origin.y
    w.show_archived(20,True);pump()
    assert current.archived_section is section
    w.show_archived(20,False);pump()
    assert current.archived_section is None and section.revealer.get_parent() is None
    toggle_hold_column(w,current.stack);pump(.06)
    section=current.hold_section
    assert section and 0<section.revealer.get_height()<section.get_height()
    assert [tile.card['id'] for tile in current.drop.widgets]==[99]
    pump()
    toggle_hold_column(w,current.stack);pump(.06)
    assert current.hold_section is None and section.revealer.get_parent() is current.body
    toggle_hold_column(w,current.stack);pump()
    assert current.hold_section is section
    toggle_hold_column(w,current.stack);pump()
    assert current.hold_section is None
    assert [tile.card['id'] for tile in current.drop.widgets]==[99,100]
    assert w.find_card(100)['labels']==[held] and not store.operations()
    settings=Gtk.Settings.get_default();settings.set_property('gtk-enable-animations',False)
    w.show_archived(20,True);pump(.03)
    assert current.archived_section.revealer.get_child_revealed()
    section=current.archived_section
    w.show_archived(20,False)
    assert current.archived_section is None and section.revealer.get_parent() is None
    toggle_hold_column(w,current.stack)
    assert current.hold_section.revealer.get_child_revealed()
    toggle_hold_column(w,current.stack)
    assert current.hold_section is None and len(current.drop.widgets)==2
    settings.set_property('gtk-enable-animations',True)
    def finish_without_jump(section):
        motion=section.revealer
        if motion.animation:motion.animation.pause()
        motion.position=.001
        motion.queue_resize();pump(.04)
        before=current.get_height()
        motion.finish();pump(.04)
        assert abs(before-current.get_height())<=2,(before,current.get_height())
    w.show_archived(20,True);pump()
    section=current.archived_section
    w.show_archived(20,False)
    finish_without_jump(section)
    toggle_hold_column(w,current.stack);pump()
    section=current.hold_section
    toggle_hold_column(w,current.stack)
    # Returning cards already participate in the closing motion; completion
    # must not insert a new row after the section has disappeared.
    returned=list(current.drop.widgets)
    assert [tile.card['id'] for tile in returned]==[99,100]
    if current.active_revealer.animation:current.active_revealer.animation.skip()
    finish_without_jump(section)
    assert current.drop.widgets==returned
    w.close()
print('PASS shared section slides: show/hide, internal fold, reversal, stable columns, retained labels and reduced motion')
