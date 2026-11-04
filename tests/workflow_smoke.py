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


app=Adw.Application(application_id='cat.ceskfreixas.Campbase.WorkflowCheck');app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
with tempfile.TemporaryDirectory() as folder:
    store=Store(folder);store.set_setting('auto_sync',False)
    held={'id':9,'title':'On hold','color':'E9AD0C'}
    card={'id':99,'stackId':10,'boardId':1,'title':'Active example','description':'',
          'order':0,'archived':False,'labels':[]}
    store.put('snapshot',{'boards':[{'id':1,'title':'Workflow example','labels':[held],
        'permissions':{'PERMISSION_EDIT':True,'PERMISSION_MANAGE':True}}],
        'stacks':{'1':[{'id':10,'title':'Triage','cards':[card]},
                       {'id':20,'title':'In progress','cards':[dict(card,id=100,stackId=20,labels=[held],title='Paused example')]},
                       {'id':30,'title':'Not now','cards':[dict(card,id=101,stackId=30,title='Deferred example')]}]}})
    remember_creator(store,'stack',30,{'uid':'test','displayname':'Test Creator'})
    remember_creator(store,'stack',10,{'uid':'test','displayname':'Test Creator'})
    w=Window(app,store,True);w.set_default_size(1100,950);w.present();settle()
    assert not column(w,30).not_now and not column(w,20).hold_section
    dialog=WorkflowDialog(w,w.snapshot['boards'][0],20);dialog.present(w);wait_presented(dialog)
    assert dialog.stacks[dialog.stack_choice.get_selected()]['id']==30 and dialog.labels[dialog.label_choice.get_selected()]['id']==9
    assert None not in dialog.stacks and None not in dialog.labels
    dialog.enabled.set_active(True);dialog.apply();settle()
    assert options(store,1)['not_now_stack']==30
    assert len(w.stacks())==3 and len(w.snapshot['boards'][0]['labels'])==1
    assert column(w,30).not_now and not column(w,30).expanded
    rail=column(w,30);triage=column(w,10);row=rail.get_parent()
    assert isinstance(row,TriageRow) and triage.get_parent() is row
    _,left=triage.compute_bounds(row);_,right=rail.compute_bounds(row)
    assert abs(left.origin.y-right.origin.y)<1 and right.origin.x>=left.origin.x+left.size.width
    assert right.size.width<=54 and right.size.height>=left.size.height
    assert not column(w,30).drop.widgets[0].get_mapped()
    assert not any(isinstance(item,Gtk.Label) and item.get_label().startswith('Creat per') for item in descendants(column(w,30)))
    assert any(isinstance(item,Gtk.Label) and item.get_label().startswith('Creat per') for item in descendants(column(w,10)))
    assert column(w,20).hold_section.widgets[0].card['id']==100
    assert not column(w,20).drop.widgets
    # Pausing in another column uses one durable operation and the native root target.
    source=column(w,10).drop.widgets[0];dest=column(w,20)
    w.drag_session.begin(source,source.card);settle()
    ok,bounds=dest.hold_section.compute_bounds(dest);assert ok
    x,y=bounds.origin.x+10,bounds.origin.y+10
    dest.drop.motion(None,x,y);settle()
    assert w.drag_session.target is dest.hold_section.drop
    assert dest.drop.drop(None,'campbase-card:99',x,y)
    w.drag_session.finish();settle()
    assert w.find_card(99)['stackId']==20 and w.find_card(99)['labels']==[held]
    assert len(store.operations())==1
    w._undo_toast.emit('button-clicked');settle()
    assert w.find_card(99)['stackId']==10 and not w.find_card(99)['labels'] and not store.operations()
    # Resume within the same column, including the correct source placeholder.
    source=column(w,20).hold_section.widgets[0];dest=column(w,20)
    w.drag_session.begin(source,source.card);settle()
    assert w.drag_session.source_column is dest
    assert dest.drop.drop(None,'campbase-card:100',10,0)
    w.drag_session.finish();settle()
    assert not w.find_card(100)['labels'] and column(w,20).drop.widgets
    w._undo_toast.emit('button-clicked');settle()
    assert w.find_card(100)['labels']==[held] and not store.operations()
    # A collapsed deferred row accepts cards, and Undo returns them to their source.
    source=column(w,10).drop.widgets[0];dest=column(w,30)
    w.drag_session.begin(source,source.card);settle()
    assert dest.drop.drop(None,'campbase-card:99',10,10)
    w.drag_session.finish();settle()
    assert w.find_card(99)['stackId']==30 and not column(w,30).expanded
    w._undo_toast.emit('button-clicked');settle()
    assert w.find_card(99)['stackId']==10 and not store.operations()
    # Folding is persistent; search temporarily reveals matching deferred cards.
    column(w,30).fold_button.emit('clicked');settle()
    assert options(store,1)['not_now_expanded'] and column(w,30).drop.widgets[0].get_mapped()
    assert not any(isinstance(item,Gtk.Label) and item.get_label().startswith('Creat per') for item in descendants(column(w,30)))
    column(w,30).fold_button.emit('clicked');w.render();settle()
    assert not column(w,30).expanded
    w.query='deferred';w.render();settle()
    assert column(w,30).expanded and len(column(w,30).drop.widgets)==1
    w.query='';w.render();settle()
    assert not column(w,30).expanded
    # The editor switch and shared label picker stay in sync; closing does not write.
    editor=CardDialog(w,20,w.find_card(100));editor.present(w);wait_presented(editor)
    assert all(item.get_tooltip_text()!=held['title'] for item in descendants(editor.labels))
    manager=LabelManagerDialog(editor.labels);manager.display(w.snapshot['boards'][0])
    assert not manager.rows
    protected=LabelEditDialog(manager,held);protected.perform()
    assert protected.status.get_visible() and not store.operations()
    create=NewLabelDialog(editor.labels);create.name.set_text(held['title']);create.create()
    assert create.status.get_visible() and len(editor.labels.labels)==1
    editor.hold_switch.set_active(False)
    assert 9 not in editor.labels.selected
    assert 9 not in editor.labels.buttons
    editor.hold_switch.set_active(True)
    assert 9 in editor.labels.selected
    editor.force_close();settle()
    assert not store.operations()
    # Both sections share folding, visibility menus and native card placement.
    w.show_archived(20,True);settle()
    current=column(w,20)
    for section in (current.hold_section,current.archived_section):
        assert isinstance(section,CardSection)
        assert isinstance(section.get_first_child(),Gtk.Separator)
        section.fold.emit('clicked');settle();assert not section.body.get_visible()
    w.render();settle()
    current=column(w,20)
    for section in (current.hold_section,current.archived_section):
        assert section.collapsed and not section.body.get_visible()
        section.fold.emit('clicked');settle();assert section.body.get_visible()
    # Each visibility menu closes before replacing its own section.
    menu=current.hold_section.menu;menu.popup();settle()
    assert menu.activate_action('section.hide',None);settle()
    assert not column(w,20).hold_section and w.find_card(100)['labels']==[held]
    toggle_hold_column(w,w.stacks()[1]);settle()
    current=column(w,20);menu=current.archived_section.menu;menu.popup();settle()
    assert menu.activate_action('section.hide',None);settle()
    assert not column(w,20).archived_section
    w.show_archived(20,True);settle();current=column(w,20)
    # Resume is the same reversible first card control as restore for archives.
    current.hold_section.cards[0].restore_button.emit('clicked');settle()
    assert not w.find_card(100)['labels']
    w._undo_toast.emit('button-clicked');settle()
    assert w.find_card(100)['labels']==[held] and not store.operations()
    # A sidebar menu for a different board must never configure the current board's columns.
    snapshot=store.get('snapshot');snapshot['boards'].append({'id':2,'title':'Other board','labels':[]})
    snapshot['stacks']['2']=[{'id':40,'title':'Other column','cards':[]}]
    store.put('snapshot',snapshot);w.render();settle()
    dialog=WorkflowDialog(w,w.snapshot['boards'][1]);dialog.present(w);wait_presented(dialog)
    assert [item['id'] for item in dialog.stacks if item]==[40]
    dialog.enabled.set_active(True);dialog.apply();settle()
    assert options(store,2)['not_now_stack'] not in {10,20,30,40}
    assert w.board_id==1 and options(store,1)['not_now_stack']==30
    # Disabling local presentation leaves all shared cards and labels intact.
    toggle_hold_column(w,w.stacks()[1]);settle()
    assert not column(w,20).hold_section and column(w,20).drop.widgets[0].card['labels']==[held]
    save_options(store,1,not_now_enabled=False);w.render();settle()
    assert not any(isinstance(item,Column) and item.stack['id']==30 for item in descendants(w.board_body))
    assert len(w.stacks())==3 and not store.operations()
    w.query='deferred';w.render();settle()
    assert not any(isinstance(item,Column) and item.stack['id']==30 for item in descendants(w.board_body))
    w.query='';w.render();settle()
    editor=CardDialog(w,10)
    assert 30 not in {item['id'] for item in editor.stacks}
    # A notification can still open an existing deferred card without changing its column.
    editor=CardDialog(w,30,w.find_card(101))
    assert editor.stacks[editor.column.get_selected()]['id']==30
    # If a reused first column is hidden, the global New Card action chooses a visible column.
    save_options(store,1,not_now_stack=10);w.render();settle()
    w.new_card();editor=w.get_visible_dialog();wait_presented(editor)
    assert editor.stacks[editor.column.get_selected()]['id']==20
    editor.force_close();settle()
    save_options(store,1,not_now_stack=30);w.render();settle()
    # Existing resources can be selected without a connection or server writes.
    w.demo=False
    original_run=w.engine.run
    w.engine.run=lambda *_: (_ for _ in ()).throw(AssertionError('Existing setup must work offline'))
    dialog=WorkflowDialog(w,w.snapshot['boards'][0],20);dialog.present(w);wait_presented(dialog)
    dialog.enabled.set_active(True);dialog.apply();settle()
    w.engine.run=original_run
    assert column(w,20).hold_section and column(w,30).not_now
    # The board switch hides all paused sections without changing shared labels.
    dialog=WorkflowDialog(w,w.snapshot['boards'][0]);dialog.present(w);wait_presented(dialog)
    dialog.configure_hold.set_active(False);dialog.apply();settle()
    assert not column(w,20).hold_section and w.find_card(100)['labels']==[held]
    dialog=WorkflowDialog(w,w.snapshot['boards'][0]);dialog.present(w);wait_presented(dialog)
    dialog.configure_hold.set_active(True);dialog.apply();settle()
    assert column(w,20).hold_section
    # Read-only accounts can configure local views, but cannot create resources or drag.
    snapshot=store.get('snapshot');snapshot['boards'][0]['permissions']={'PERMISSION_EDIT':False,'PERMISSION_MANAGE':False};store.put('snapshot',snapshot)
    w.render();settle()
    dialog=WorkflowDialog(w,w.snapshot['boards'][0]);dialog.present(w);wait_presented(dialog)
    dialog.enabled.set_active(True)
    assert None not in dialog.stacks and None not in dialog.labels
    assert dialog.save.get_sensitive()
    dialog.force_close();settle()
    w.dragged_card=w.find_card(99)
    assert not column(w,20).drop.accepts()
    w.dragged_card=None
    editor=CardDialog(w,20,w.find_card(100));editor.present(w);wait_presented(editor)
    rows=[item for item in descendants(editor) if isinstance(item,Adw.SwitchRow) and item.get_title()=='En espera']
    assert len(rows)==1 and rows[0].get_active() and not rows[0].get_sensitive()
    editor.force_close();settle()
    for width in (600,1200):
        w.set_default_size(width,950);settle()
        assert column(w,30).get_width()<=w.board_body.get_width()
    w.close();settle()
# First-time setup runs through the actual serialized worker, using a synthetic API.
from test_workflow import SetupAPI
with tempfile.TemporaryDirectory() as folder:
    store=Store(folder);store.set_setting('auto_sync',False)
    api=SetupAPI();api.stacks=[{'id':1,'title':'Triatge','cards':[],'order':0}];api.uncertain=True
    store.put('snapshot',{'boards':[{'id':1,'title':'First setup','labels':[],
        'permissions':{'PERMISSION_EDIT':True,'PERMISSION_MANAGE':True}}], 'stacks':{'1':api.stacks}})
    w=Window(app,store,True);w.demo=False;w.engine.api=api;w.present();settle()
    dialog=WorkflowDialog(w,w.snapshot['boards'][0],1);dialog.present(w);wait_presented(dialog)
    dialog.enabled.set_active(True);dialog.apply()
    wait_until(lambda:dialog.closed)
    settle()
    assert api.writes==2 and options(store,1)['hold_label']==9
    assert column(w,10).not_now and column(w,1).hold_section
    assert not store.operations()
    # A dialog opened under a different account must never write local roles to the new one.
    dialog=WorkflowDialog(w,w.snapshot['boards'][0]);dialog.present(w);wait_presented(dialog)
    before=options(store,1);w.engine.api=None
    dialog.enabled.set_active(False);dialog.apply()
    assert options(store,1)==before
    dialog.force_close();settle();w.close();settle()
print('PASS optional setup, shared resource reuse, drag pause/resume/defer, undo, fold/search, offline and read-only')
