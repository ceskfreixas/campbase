# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Real input-event regression test. Use only an isolated Xvfb display."""
import ctypes,tempfile,time,os
import campbase
from pathlib import Path
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1');gi.require_version('GdkX11','4.0')
from gi.repository import Gtk,Adw,Gdk,GdkX11,GLib
from campbase.card_dialog import CardDialog
from campbase.__main__ import demo_snapshot
from campbase.window import Window
from campbase.storage import Store
from campbase.widgets import Column
from gui_helpers import wait_presented
app=Adw.Application(application_id='cat.ceskfreixas.Campbase.RealDragTest');app.register(None)
Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(Path(campbase.__file__).resolve().parents[1]/'data/icons'))
provider=Gtk.CssProvider();provider.load_from_path(str(Path(campbase.__file__).parent/'style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
def settle(duration=.15):
 until=time.monotonic()+duration
 while time.monotonic()<until:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  time.sleep(.005)
x11=ctypes.CDLL('libX11.so.6');xtest=ctypes.CDLL('libXtst.so.6')
x11.XOpenDisplay.argtypes=[ctypes.c_char_p];x11.XOpenDisplay.restype=ctypes.c_void_p
x11.XFlush.argtypes=[ctypes.c_void_p];x11.XCloseDisplay.argtypes=[ctypes.c_void_p]
xtest.XTestFakeMotionEvent.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_ulong]
xtest.XTestFakeButtonEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
assert os.environ.get('CAMPBASE_TEST_X11')=='1', 'Run only on a dedicated Xvfb display with CAMPBASE_TEST_X11=1'
display=x11.XOpenDisplay(os.environ['DISPLAY'].encode());assert display
x11.XKeysymToKeycode.argtypes=[ctypes.c_void_p,ctypes.c_ulong];x11.XKeysymToKeycode.restype=ctypes.c_uint
xtest.XTestFakeKeyEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]

# A caller testing a Flatpak must verify the root marker before injecting input.
# Flatpak selects its X11 socket from the launcher's DISPLAY, not --env=DISPLAY.
if not os.environ.get('CAMPBASE_TEST_DISPLAY_TOKEN'):
 # Outside Flatpak, accept only a display owned by an actual Xvfb process.
 display_number=os.environ['DISPLAY'].split('.')[0]
 isolated=False
 for process in Path('/proc').iterdir():
  if not process.name.isdigit():
   continue
  try:
   argv=(process/'cmdline').read_bytes().split(b'\0')
   isolated |= bool(argv and argv[0].rsplit(b'/',1)[-1]==b'Xvfb' and display_number.encode() in argv[1:])
  except (OSError,PermissionError):
   continue
 assert isolated, 'Refusing input: use a dedicated Xvfb display or a verified root marker'
if os.environ.get('CAMPBASE_TEST_DISPLAY_TOKEN'):
 x11.XDefaultRootWindow.argtypes=[ctypes.c_void_p];x11.XDefaultRootWindow.restype=ctypes.c_ulong
 x11.XInternAtom.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_int];x11.XInternAtom.restype=ctypes.c_ulong
 x11.XGetWindowProperty.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_long,ctypes.c_long,ctypes.c_int,ctypes.c_ulong,ctypes.POINTER(ctypes.c_ulong),ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_ulong),ctypes.POINTER(ctypes.c_ulong),ctypes.POINTER(ctypes.c_void_p)]
 atom=x11.XInternAtom(display,b'_CAMPBASE_ISOLATED_TEST_DISPLAY',1)
 assert atom, 'Refusing input: isolated Xvfb marker is missing'
 actual=ctypes.c_ulong();fmt=ctypes.c_int();count=ctypes.c_ulong();remaining=ctypes.c_ulong();data=ctypes.c_void_p()
 assert x11.XGetWindowProperty(display,x11.XDefaultRootWindow(display),atom,0,256,0,0,ctypes.byref(actual),ctypes.byref(fmt),ctypes.byref(count),ctypes.byref(remaining),ctypes.byref(data))==0
 assert fmt.value==8 and ctypes.string_at(data,count.value).decode()==os.environ['CAMPBASE_TEST_DISPLAY_TOKEN'], 'Refusing input: wrong display'
 x11.XFree.argtypes=[ctypes.c_void_p];x11.XFree(data)
 print('PASS isolated display marker verified before input',flush=True)
x11.XDefaultRootWindow.argtypes=[ctypes.c_void_p];x11.XDefaultRootWindow.restype=ctypes.c_ulong
x11.XTranslateCoordinates.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_int,ctypes.c_int,ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_ulong)]
x11.XMoveWindow.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_int]

def root_point(x,y):
 # Dialog presentation, resizing and the window manager can change the native
 # origin. Resolve it for each event instead of caching it before opening a card.
 root_x=ctypes.c_int();root_y=ctypes.c_int();child=ctypes.c_ulong()
 assert x11.XTranslateCoordinates(display,GdkX11.X11Surface.get_xid(w.get_surface()),
   x11.XDefaultRootWindow(display),0,0,ctypes.byref(root_x),ctypes.byref(root_y),ctypes.byref(child))
 transform=w.get_surface_transform();scale=w.get_scale_factor()
 return round(root_x.value+(x+transform.x)*scale),round(root_y.value+(y+transform.y)*scale)

def motion(x,y):
 root_x,root_y=root_point(x,y)
 xtest.XTestFakeMotionEvent(display,-1,root_x,root_y,0);x11.XFlush(display);settle(.05)
def button(down):
 xtest.XTestFakeButtonEvent(display,1,int(down),0);x11.XFlush(display);settle(.1)

def start_point(widget,center=False):
 # A closed Adw.Dialog can still be animating out and intercepting input.
 # Wait for the actual native input target, not a fixed animation duration.
 deadline=time.monotonic()+3
 while time.monotonic()<deadline:
  ok,bounds=widget.compute_bounds(w)
  if ok and widget.get_mapped():
   x=bounds.origin.x+(bounds.size.width/2 if center else 40)
   y=bounds.origin.y+bounds.size.height/2
   picked=w.pick(x,y,Gtk.PickFlags.DEFAULT)
   while picked and picked is not widget:
    picked=picked.get_parent()
   if picked is widget:
    return x,y
   # Reveal contextual handles through a real hover before pressing them.
   motion(x,y)
  settle(.02)
 raise AssertionError('The drag source did not become an input target after closing the dialog')
xtest.XTestFakeButtonEvent(display,1,0,0);x11.XFlush(display);settle(.1)
try:
 with tempfile.TemporaryDirectory() as path:
  store=Store(path);snapshot=demo_snapshot()
  archived_source=os.environ.get('CAMPBASE_ARCHIVED_SOURCE')=='1'
  if archived_source:snapshot['stacks']['1'][0]['cards'][0]['archived']=True
  if os.environ.get('CAMPBASE_ARCHIVE_DESTINATION')=='1':snapshot['stacks']['1'][1]['cards'][0]['archived']=True
  store.put('snapshot',snapshot);w=Window(app,store,True);w.set_default_size(1240,1000);w.present();settle(.5)
  # Native shadow extents differ between GTK versions. Translate widget
  # coordinates into X11 root coordinates before injecting pointer events.
  x11.XMoveWindow(display,GdkX11.X11Surface.get_xid(w.get_surface()),0,0);x11.XFlush(display);settle(.2)
  triage=w.board_body.get_first_child().get_next_sibling()
  workflow=triage.get_next_sibling();target_column=workflow.get_first_child().get_child()
  if archived_source:w.show_archived(triage.stack['id'],True);settle()
  source=triage.archived_section.cards[0] if archived_source else triage.drop.widgets[0]
  target=target_column.drop.widgets[0]
  archive_drop=os.environ.get('CAMPBASE_ARCHIVE_DROP')=='1'
  if archive_drop:
   w.show_archived(target_column.stack['id'],True);settle()
   target=target_column.archived_section
  use_handle=os.environ.get('CAMPBASE_DRAG_HANDLE')=='1'
  origin=source.drag_handle if use_handle else source
  ok,s=origin.compute_bounds(w);assert ok
  ok,t=target.compute_bounds(w);assert ok
  sx,sy=start_point(origin,center=True)
  tx,ty=t.origin.x+40,t.origin.y+(t.size.height/2 if archive_drop else 4)
  if not use_handle:
   motion(sx,sy);button(True);button(False);settle(.2)
   opened=w.get_visible_dialog();assert isinstance(opened,CardDialog)
   wait_presented(opened)
   closed=[];opened.connect('closed',lambda *_unused:closed.append(True))
   opened.force_close()
   deadline=time.monotonic()+3
   while (not closed or opened.get_mapped() or w.get_visible_dialog() is opened) and time.monotonic()<deadline:settle(.05)
   assert closed and not opened.get_mapped() and w.get_visible_dialog() is not opened
   # This is a separate gesture, after closing the editor. Respect the desktop's
   # multi-click interval rather than accidentally synthesizing a double-click.
   settle(Gtk.Settings.get_default().get_property('gtk-double-click-time')/1000+.05)
   ok,t=target.compute_bounds(w);assert ok
   # Start the distinct drag away from the click point: opening/closing the
   # editor immediately must not turn this synthetic press into a double-click.
   sx,sy=start_point(origin)
   tx,ty=t.origin.x+40,t.origin.y+(t.size.height/2 if archive_drop else 4)
  if os.environ.get('CAMPBASE_TEST_RELOCATE_WINDOW')=='1':
   x11.XMoveWindow(display,GdkX11.X11Surface.get_xid(w.get_surface()),100,35);x11.XFlush(display);settle(.2)
  motion(sx,sy);button(True)
  # GTK 4.14 starts a drag only after both a distance threshold and a 100 ms
  # gesture timer. A single early motion is ignored, even if we wait afterward.
  # Keep moving within this same press, as a person does, until GTK starts DnD.
  for step in range(1,7):
   motion(sx+4*step,sy+step)
   if w.dragged_card:
    break
  deadline=time.monotonic()+2
  while not w.dragged_card and time.monotonic()<deadline:settle(.05)
  assert w.dragged_card and w.dragged_card['id']==101
  assert source.has_css_class('drag-source')
  drag=(source.handle_drag if use_handle else source.drag).controller.get_drag();assert drag
  assert Gtk.DragIcon.get_for_drag(drag).get_child() is not None
  for i in range(1,15):motion(sx+24+(tx-sx-24)*i/14,sy+5+(ty-sy-5)*i/14)
  settle(.2)
  if archive_drop:
   # Follow the destination after the active-card insertion marker appears.
   # Entering the archive itself must then preserve its on-screen position.
   ok,t=target.compute_bounds(w);assert ok
   motion(t.origin.x+40,t.origin.y+t.size.height/2);settle(.2)
   if target.cards:
    assert not target.has_css_class('archive-drop-active') and target.drop.placeholder.get_mapped()
   else:assert target.has_css_class('archive-drop-active')
   assert not target_column.has_css_class('drop-active')
   ok,stable=target.compute_bounds(w);assert ok
   assert abs(stable.origin.y-t.origin.y)<1
  else:
   assert target_column.has_css_class('drop-active') and target_column.drop.placeholder.get_mapped()
  button(False);settle(.5)
  assert w.find_card(101)['stackId']==2
  assert not w.dragged_card and not w.drag_session.target
  assert len(store.operations())==1
  if not archive_drop:assert w.cards_in_stack(2)[0]['id']==101
  assert bool(w.find_card(101).get('archived'))==archive_drop
  print('PASS actual native mouse drag, floating preview, insertion marker and queued move',flush=True)
  editor=CardDialog(w,1);editor.present(w);settle()
  texture=Gdk.MemoryTexture.new(4,4,Gdk.MemoryFormat.R8G8B8A8,GLib.Bytes.new(bytes([40,120,90,255])*16),16)
  editor.description.view.get_clipboard().set_content(Gdk.ContentProvider.new_for_value(texture))
  editor.description.view.grab_focus();settle()
  control=x11.XKeysymToKeycode(display,0xffe3);key_v=x11.XKeysymToKeycode(display,ord('v'))
  for key,down in [(control,1),(key_v,1),(key_v,0),(control,0)]:
   xtest.XTestFakeKeyEvent(display,key,down,0)
  x11.XFlush(display);settle(.5)
  assert len(editor.description.local_images())==1
  print('PASS actual Ctrl+V image paste through native keyboard events',flush=True)
  closed=[];editor.connect('closed',lambda *_unused:closed.append(True));editor.force_close()
  deadline=time.monotonic()+3
  while (not closed or editor.get_mapped()) and time.monotonic()<deadline:settle(.05)
  assert closed and not editor.get_mapped()
  from campbase.notifications import NotificationsDialog
  inbox=NotificationsDialog(w);inbox.present(w);settle(.4)
  ok,bounds=inbox.get_child().compute_bounds(w);assert ok
  motion(bounds.origin.x+bounds.size.width/2,bounds.origin.y+20);button(True);button(False)
  assert inbox.get_mapped()
  outside_closed=[];inbox.connect('closed',lambda *_unused:outside_closed.append(True))
  motion(30,max(100,bounds.origin.y-20));button(True);button(False)
  deadline=time.monotonic()+3
  while (not outside_closed or inbox.get_mapped()) and time.monotonic()<deadline:settle(.05)
  assert outside_closed and not inbox.get_mapped() and inbox.outside_click.get_widget() is None
  print('PASS actual outside click dismisses Notifications and inside click preserves it',flush=True)
  w.close();settle()
finally:
 xtest.XTestFakeButtonEvent(display,1,0,0)
 x11.XFlush(display)
 x11.XCloseDisplay(display)
