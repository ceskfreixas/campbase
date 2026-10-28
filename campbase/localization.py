# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Live bindings for owned UI text, independent of Python widget wrappers."""
import weakref
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib
from .i18n import Message

_bindings = {}
_callbacks = []
_updating = False


def _discard(key):
    _bindings.pop(key, None)


def _binding(obj):
    key = hash(obj)
    if key not in _bindings:
        # A GObject can outlive its Python wrapper, especially inside Flatpak.
        # Native weak references preserve bindings without retaining the widget.
        _bindings[key] = {'ref': obj.weak_ref(_discard, key)}
    return _bindings[key]


def updating():
    return _updating


def render(value):
    return value.render() if isinstance(value, Message) else value


def widget(obj, **properties):
    for name, value in properties.items():
        if name == 'text' and isinstance(obj, (Gtk.Editable, Gtk.TextBuffer)):
            continue
        if isinstance(value, Message):
            _binding(obj).setdefault('properties', {})[name] = value
            obj.set_property(name.replace('_', '-'), value.render())
    if hasattr(obj, 'get_selected') and hasattr(obj, 'get_model'):
        _binding(obj)['selector'] = True
    return obj


def create(constructor, *args, **kwargs):
    properties = {key: value for key, value in kwargs.items() if isinstance(value, Message)}
    obj = constructor(*args, **{key: render(value) for key, value in kwargs.items()})
    return widget(obj, **properties)


def text(obj, name, value):
    # Entry/buffer contents and their undo history belong to the user.
    editable = name == 'text' and isinstance(obj, (Gtk.Editable, Gtk.TextBuffer))
    if not editable:
        binding = _binding(obj) if isinstance(value, Message) else _bindings.get(hash(obj))
        if binding is not None:
            property_name = 'label' if name == 'text' and isinstance(obj, Gtk.Label) else name
            binding.get('properties', {}).pop(property_name, None)
            setters = binding.setdefault('setters', {})
            if isinstance(value, Message):
                setters[name] = value
            else:
                setters.pop(name, None)
    return getattr(obj, 'set_' + name)(render(value))


def accessible(obj, properties, values):
    binding = _binding(obj) if any(isinstance(value, Message) for value in values) else _bindings.get(hash(obj))
    if binding is not None:
        labels = binding.setdefault('accessible', {})
        for prop, value in zip(properties, values):
            if isinstance(value, Message):
                labels[prop] = value
            else:
                labels.pop(prop, None)
    obj.update_property(properties, [render(value) for value in values])


def strings(values):
    values = list(values)
    model = Gtk.StringList.new([render(value) for value in values])
    if any(isinstance(value, Message) for value in values):
        _binding(model)['strings'] = values
    return model


def selection(obj, callback):
    return obj.connect('notify::selected', lambda *args: None if _updating else callback(*args))


def menu_append(menu, title, action, accelerator=None):
    position = menu.get_n_items()
    item = Gio.MenuItem.new(render(title), action)
    if accelerator:
        item.set_attribute_value('accel', GLib.Variant('s', accelerator))
    menu.append_item(item)
    if isinstance(title, Message):
        _binding(menu).setdefault('items', {})[position] = (title, action, accelerator)


def stack_title(stack, child, name, title):
    return widget(stack.add_titled(child, name, render(title)), title=title)


def response(dialog, name, title):
    dialog.add_response(name, render(title))
    if isinstance(title, Message):
        _binding(dialog).setdefault('responses', {})[name] = title


def on_change(callback):
    _callbacks.append(weakref.WeakMethod(callback))


def _refresh_models(live):
    selections = [(obj, obj.get_selected()) for obj, binding in live if binding.get('selector')]
    for obj, _index in selections:
        obj.freeze_notify()
    try:
        for obj, binding in live:
            for index, value in enumerate(binding.get('strings', [])):
                translated = render(value)
                if obj.get_string(index) != translated:
                    obj.splice(index, 1, [translated])
        for obj, index in selections:
            obj.set_selected(index)
    finally:
        for obj, _index in selections:
            obj.thaw_notify()


def _refresh_object(obj, binding):
    for name, value in binding.get('properties', {}).items():
        obj.set_property(name.replace('_', '-'), value.render())
    for name, value in binding.get('setters', {}).items():
        getattr(obj, 'set_' + name)(value.render())
    values = binding.get('accessible', {})
    if values:
        obj.update_property(list(values), [value.render() for value in values.values()])
    for name, value in binding.get('responses', {}).items():
        obj.set_response_label(name, value.render())
    for position, (title, action, accelerator) in binding.get('items', {}).items():
        item = Gio.MenuItem.new(title.render(), action)
        if accelerator:
            item.set_attribute_value('accel', GLib.Variant('s', accelerator))
        obj.remove(position)
        obj.insert_item(position, item)


def refresh():
    global _updating
    _updating = True
    try:
        live = [(obj, binding) for binding in list(_bindings.values())
                if (obj := binding['ref']()) is not None]
        _refresh_models(live)
        for obj, binding in live:
            _refresh_object(obj, binding)
        for reference in list(_callbacks):
            callback = reference()
            if callback is None:
                _callbacks.remove(reference)
            else:
                callback()
    finally:
        _updating = False
