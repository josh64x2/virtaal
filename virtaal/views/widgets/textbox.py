#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2009 Zuza Software Foundation
#
# This file is part of Virtaal.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>.

import gobject
import gtk
import logging
from gobject import SIGNAL_RUN_FIRST, SIGNAL_RUN_LAST, TYPE_BOOLEAN, TYPE_NONE, TYPE_PYOBJECT, TYPE_STRING

from translate.misc.typecheck import accepts, Self, IsOneOf
from translate.storage.placeables import base, general, parse as elem_parse, terminology, StringElem

from virtaal.views import placeablesguiinfo


class TextBox(gtk.TextView):
    """
    A C{gtk.TextView} extended to work with our nifty L{StringElem} parsed
    strings.
    """

    __gtype_name__ = 'TextBox'
    __gsignals__ = {
        'after-apply-tags': (SIGNAL_RUN_FIRST, TYPE_NONE, (TYPE_PYOBJECT,)),
        'before-apply-tags': (SIGNAL_RUN_FIRST, TYPE_NONE, (TYPE_PYOBJECT,)),
        'key-pressed': (SIGNAL_RUN_LAST, TYPE_BOOLEAN, (TYPE_PYOBJECT, TYPE_STRING)),
    }

    SPECIAL_KEYS = {
        'alt-down':  [(gtk.keysyms.Down,  gtk.gdk.MOD1_MASK)],
        'alt-left':  [(gtk.keysyms.Left,  gtk.gdk.MOD1_MASK)],
        'alt-right': [(gtk.keysyms.Right, gtk.gdk.MOD1_MASK)],
        'enter':     [(gtk.keysyms.Return, 0), (gtk.keysyms.KP_Enter, 0)],
    }
    """A table of name-keybinding mappings. The name (key) is passed as the
    second parameter to the 'key-pressed' event."""
    unselectables = [StringElem]
    """A list of C{StringElem} sub-classes that should not be selectable with
    Alt+Left or Alt+Right."""

    # INITIALIZERS #
    def __init__(self, main_controller, text=None, selector_textbox=None):
        """Constructor.
        @type  main_controller: L{virtaal.controllers.main_controller}
        @param main_controller: The main controller instance.
        @type  text: String
        @param text: The initial text to set in the new text box. Optional.
        @type  selector_textbox: C{TextBox}
        @param selector_textbox: The text box in which placeable selection
            (@see{select_elem}) should happen. Optional."""
        super(TextBox, self).__init__()
        self.buffer = self.get_buffer()
        self.elem = None
        self.main_controller = main_controller
        self.selector_textbox = selector_textbox or self
        self.selected_elem = None
        self.selected_elem_index = None
        self.__connect_default_handlers()
        self.placeables_controller = main_controller.placeables_controller
        if self.placeables_controller is None:
            self.__controller_connect_id = main_controller.connect('controller-registered', self.__on_controller_register)
        if text:
            self.set_text(text)

    def __connect_default_handlers(self):
        self.connect('key-press-event', self._on_key_pressed)
        self.buffer.connect('changed', self._on_changed)
        self.buffer.connect('insert-text', self._on_insert_text)
        self.buffer.connect('delete-range', self._on_delete_range)


    # OVERRIDDEN METHODS #
    def get_stringelem(self):
        return elem_parse(self.get_text(), self.placeables_controller.parsers)

    def get_text(self, start_iter=None, end_iter=None):
        """Return the text rendered in this text box.
            Uses C{gtk.TextBuffer.get_text()}."""
        if start_iter is None:
            start_iter = self.buffer.get_start_iter()
        if end_iter is None:
            end_iter = self.buffer.get_end_iter()
        return self.buffer.get_text(start_iter, end_iter)

    @accepts(Self(), [[IsOneOf(StringElem, str, unicode)]])
    def set_text(self, text):
        """Set the text rendered in this text box.
            Uses C{gtk.TextBuffer.set_text()}.
            @type  text: str|unicode|L{StringElem}
            @param text: The text to render in this text box."""
        self.selected_elem = None
        self.selected_elem_index = None

        self.buffer.handler_block_by_func(self._on_delete_range)
        self.buffer.handler_block_by_func(self._on_insert_text)
        self.buffer.set_text(unicode(text))
        self.buffer.handler_unblock_by_func(self._on_delete_range)
        self.buffer.handler_unblock_by_func(self._on_insert_text)

        self.update_tree(text)


    # METHODS #
    @accepts(Self(), [StringElem])
    def add_default_gui_info(self, elem):
        """Add default GUI info to string elements in the tree that does not
            have any GUI info.

            Only leaf nodes are (currently) extended with a C{StringElemGUI}
            (or sub-class) instance. Other nodes has C{gui_info} set to C{None}.

            @type  elem: StringElem
            @param elem: The root of the string element tree to add default
                GUI info to.
            """
        if not isinstance(elem, StringElem):
            return

        if not hasattr(elem, 'gui_info') or not elem.gui_info:
            elem.gui_info = self.placeables_controller.get_gui_info(elem)(elem=elem, textbox=self)

        for sub in elem.sub:
            self.add_default_gui_info(sub)

    @accepts(Self(), [StringElem, bool])
    def apply_tags(self, elem, include_subtree=True):
        offset = self.elem.elem_offset(elem)
        if offset >= 0:
            #print '[%s] at offset %d' % (unicode(elem).encode('utf-8'), offset)
            self.emit('before-apply-tags', elem)

            iters = (
                self.buffer.get_iter_at_offset(offset),
                self.buffer.get_iter_at_offset(offset + len(elem))
            )
            if getattr(elem, 'gui_info', None):
                tag = elem.gui_info.create_tag()
                if tag:
                    if not include_subtree or \
                            elem.gui_info.fg != placeablesguiinfo.StringElemGUI.fg or \
                            elem.gui_info.bg != placeablesguiinfo.StringElemGUI.bg:
                        self.buffer.get_tag_table().add(tag)
                        self.buffer.apply_tag(tag, iters[0], iters[1])

        if include_subtree:
            for sub in elem.sub:
                if isinstance(sub, StringElem):
                    self.apply_tags(sub)

        self.emit('after-apply-tags', elem)

    @accepts(Self(), [int])
    def move_elem_selection(self, offset):
        if self.selector_textbox.selected_elem_index is None:
            if offset <= 0:
                self.selector_textbox.select_elem(offset=offset)
            else:
                self.selector_textbox.select_elem(offset=offset-1)
        else:
            self.selector_textbox.select_elem(offset=self.selector_textbox.selected_elem_index + offset)

    @accepts(Self(), [[StringElem, None], [int, None]])
    def select_elem(self, elem=None, offset=None):
        if (elem is None and offset is None) or (elem is not None and offset is not None):
            raise ValueError('Exactly one of "elem" or "offset" must be specified.')

        filtered_elems = [e for e in self.elem.depth_first() if e.__class__ not in self.unselectables]
        if not filtered_elems:
            return

        if elem is None and offset is not None:
            return self.select_elem(elem=filtered_elems[offset % len(filtered_elems)])

        if not elem in filtered_elems:
            return

        # Reset the default tag for the previously selected element
        if self.selected_elem:
            self.selected_elem.gui_info = None
            self.add_default_gui_info(self.selected_elem)

        i = 0
        for fe in filtered_elems:
            if fe is elem:
                break
            i += 1
        self.selected_elem_index = i
        self.selected_elem = elem
        elem.gui_info = placeablesguiinfo.StringElemGUI(elem, self, fg='#000000', bg='#90ee90')
        self.apply_tags(self.elem, include_subtree=False)
        self.apply_tags(self.elem)
        self.apply_tags(elem, include_subtree=False)
        cursor_offset = self.elem.find(self.selected_elem) + len(self.selected_elem)
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(cursor_offset))

    @accepts(Self(), [[StringElem, basestring, None]])
    def update_tree(self, text=None):
        if not self.placeables_controller:
            return
        if text is None:
            text = self.get_text().decode('utf-8')
        if not isinstance(text, StringElem):
            text = elem_parse(unicode(text), self.placeables_controller.parsers)
            self.add_default_gui_info(text)
        self.elem = text

        tagtable = self.buffer.get_tag_table()
        def remtag(tag, data):
            tagtable.remove(tag)
        # FIXME: The following line caused the program to segfault, so it's removed (for now).
        #tagtable.foreach(remtag)
        # At this point we have a tree of string elements with GUI info.
        self.apply_tags(text, include_subtree=False)
        self.apply_tags(text)

    def __delayed_update_tree(self):
        gobject.idle_add(self.update_tree)


    # EVENT HANDLERS #
    def _on_changed(self, buffer):
        pass

    def __on_controller_register(self, main_controller, controller):
        if controller is main_controller.placeables_controller:
            self.placeables_controller = controller
            main_controller.disconnect(self.__controller_connect_id)

    def _on_delete_range(self, buffer, start_iter, end_iter):
        if not self.elem:
            return

        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter())
        start_offset = start_iter.get_offset()
        end_offset = end_iter.get_offset()

        if text[start_offset:end_offset] == '\n' and text[:start_offset].endswith('\\n'):
            start_iter.set_offset(start_offset-2)

        start_elem = self.elem.elem_at_offset(start_offset)
        end_elem = self.elem.elem_at_offset(end_offset)

        #print '{%s} %s[%s]%s [%s|%s] (%d, %d)' % (
        #    repr(self.elem),
        #    text[:start_offset],
        #    text[start_offset:end_offset],
        #    text[end_offset:],
        #    repr(start_elem), repr(end_elem),
        #    start_offset, end_offset
        #)

        if start_elem is not None and not start_elem.iseditable:
            if start_elem is end_elem and start_offset == self.elem.elem_offset(end_elem):
                # Delete was pressed before a placeable
                end_iter.set_offset(end_offset + len(end_elem) - 1)
            elif start_offset == (self.elem.elem_offset(start_elem) + len(start_elem) - 1) and end_offset - start_offset == 1:
                # Backspace was pressed after a placeable
                start_iter.set_offset(self.elem.elem_offset(start_elem))

        #for i in (start_iter.get_offset(), end_iter.get_offset()-1):
        #    elem = self.elem.elem_at_offset(i)
        #    if not elem:
        #        continue
        #    if self.elem and not elem.iseditable:
        #        self.buffer.stop_emission('delete-range')
        #        return True

        self.__delayed_update_tree()

    def _on_insert_text(self, buffer, iter, ins_text, length):
        if not self.elem:
            return

        elem = self.elem.elem_at_offset(iter.get_offset())
        if not elem:
            return
        #between_elems = (iter.get_offset() == self.elem.elem_offset(elem)) or (iter.get_offset() == len(self.elem))
        #if self.elem and not elem.iseditable and not between_elems:
        #    self.buffer.stop_emission('insert-text')
        #    return True

        self.__delayed_update_tree()

    def _on_key_pressed(self, widget, event, *args):
        evname = None
        # Alt-Left
        if event.keyval == gtk.keysyms.Left and event.state & gtk.gdk.MOD1_MASK:
            self.move_elem_selection(-1)
        # Alt-Right
        elif event.keyval == gtk.keysyms.Right and event.state & gtk.gdk.MOD1_MASK:
            self.move_elem_selection(1)

        for name, keyslist in self.SPECIAL_KEYS.items():
            for keyval, state in keyslist:
                if event.keyval == keyval and event.state == (state | gtk.gdk.MOD2_MASK):
                    evname = name
        return self.emit('key-pressed', event, evname)