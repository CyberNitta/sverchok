# This file is part of project Sverchok. It's copyrighted by the contributors
# recorded in the version control history of the file, available from
# its original location https://github.com/nortikin/sverchok/commit/master
#
# SPDX-License-Identifier: GPL3
# License-Filename: LICENSE

"""
Purpose of this module is centralization of update events.

For now it can be used in debug mode for understanding which event method are triggered by Blender
during evaluation of Python code.

Details: https://github.com/nortikin/sverchok/issues/3077
"""


from enum import Enum, auto
from typing import NamedTuple, Union, List
from itertools import takewhile

from bpy.types import Node, NodeTree

from sverchok.utils.context_managers import sv_preferences
from sverchok.core.update_system import process_from_nodes


class BlenderEventsTypes(Enum):
    tree_update = auto()  # this updates is calling last with exception of creating new node
    monad_tree_update = auto()
    node_update = auto()  # it can be called last during creation new node event
    add_node = auto()   # it is called first in update wave
    copy_node = auto()  # it is called first in update wave
    free_node = auto()  # it is called first in update wave
    add_link_to_node = auto()  # it can detects only manually created links
    node_property_update = auto()  # can be in correct in current implementation
    undo = auto()  # changes in tree does not call any other update events
    frame_change = auto()

    def print(self, updated_element=None):
        event_name = f"EVENT: {self.name: <30}"
        if updated_element is not None:
            element_data = f"IN: {updated_element.bl_idname: <25} INSTANCE: {updated_element.name: <25}"
        else:
            element_data = ""
        print(event_name + element_data)


class SverchokEventsTypes(Enum):
    add_node = auto()
    copy_node = auto()
    free_node = auto()
    node_property_update = auto()
    node_link_update = auto()
    undo = auto()
    undefined = auto()  # probably should be deleted
    frame_change = auto()

    def print(self, updated_element=None):
        event_name = f"SVERCHOK EVENT: {self.name: <21}"
        element_data = f"NODE: {updated_element.name}" if updated_element else ""
        print(event_name + element_data)

    def get_draw_method_name(self):
        try:
            return DRAW_METHODS[self]
        except KeyError:
            raise KeyError(f"Event={self.name} does not have related draw method")


EVENT_CONVERSION = {
    BlenderEventsTypes.tree_update: SverchokEventsTypes.undefined,
    BlenderEventsTypes.monad_tree_update: SverchokEventsTypes.undefined,
    BlenderEventsTypes.node_update: SverchokEventsTypes.undefined,
    BlenderEventsTypes.add_node: SverchokEventsTypes.add_node,
    BlenderEventsTypes.copy_node: SverchokEventsTypes.copy_node,
    BlenderEventsTypes.free_node: SverchokEventsTypes.free_node,
    BlenderEventsTypes.add_link_to_node: SverchokEventsTypes.node_link_update,
    BlenderEventsTypes.node_property_update: SverchokEventsTypes.node_property_update,
    BlenderEventsTypes.undo: SverchokEventsTypes.undo,
    BlenderEventsTypes.frame_change: SverchokEventsTypes.frame_change
}


DRAW_METHODS = {
    SverchokEventsTypes.add_node: 'sv_init',
    SverchokEventsTypes.copy_node: 'sv_copy',
    SverchokEventsTypes.free_node: 'sv_free',
    SverchokEventsTypes.node_link_update: 'sv_update'
}


class SverchokEvent(NamedTuple):
    type: SverchokEventsTypes
    node: Node

    def redraw_node(self):
        if self.type in [SverchokEventsTypes.add_node, SverchokEventsTypes.copy_node]:
            getattr(self.node, self.type.get_draw_method_name())(None)  # todo not None
        else:
            getattr(self.node, self.type.get_draw_method_name())()

    def print(self):
        self.type.print(self.node)


class BlenderEvent(NamedTuple):
    type: BlenderEventsTypes
    updated_element: Union[Node, NodeTree, None]

    def convert_to_sverchok_event(self) -> SverchokEvent:
        try:
            sverchok_event_type = EVENT_CONVERSION[self.type]
            return SverchokEvent(sverchok_event_type, self.updated_element)
        except KeyError:
            raise KeyError(f"For Blender event type={self.type} Sverchek event is undefined")


class CurrentEvents:
    events_wave: List[BlenderEvent] = []
    _to_listen_new_events = True  # todo should be something more safe

    @classmethod
    def add_new_event(cls, event_type: BlenderEventsTypes, updated_element=None):
        if not cls._to_listen_new_events or event_type == BlenderEventsTypes.node_update:
            # such updates are not informative
            return

        if cls.is_in_debug_mode():
            event_type.print(updated_element)

        cls.events_wave.append(BlenderEvent(event_type, updated_element))
        cls.handle_new_event()

    @classmethod
    def handle_new_event(cls):
        if not cls.is_wave_end():
            return

        cls._to_listen_new_events = False

        sverchok_events = cls.convert_wave_to_sverchok_events()
        cls.redraw_nodes(sverchok_events)
        cls.update_nodes(sverchok_events)

        cls._to_listen_new_events = True
        cls.events_wave.clear()

    @classmethod
    def is_wave_end(cls):
        # it is not correct now but should be when this module will get control over the update events
        sign_of_wave_end = [BlenderEventsTypes.tree_update, BlenderEventsTypes.node_property_update,
                            BlenderEventsTypes.monad_tree_update, BlenderEventsTypes.undo,
                            BlenderEventsTypes.frame_change]
        return True if cls.events_wave[-1].type in sign_of_wave_end else False

    @classmethod
    def convert_wave_to_sverchok_events(cls):
        if cls.events_wave[0].type == BlenderEventsTypes.undo:
            return []  # todo should be implemented some changes test
        elif cls.events_wave[0].type == BlenderEventsTypes.frame_change:
            return []  # todo should be implemented some changes test
        elif cls.events_wave[0].type in [BlenderEventsTypes.tree_update, BlenderEventsTypes.monad_tree_update]:
            return []  # todo new links should be tested
        else:  # node changes event
            all_events_of_first_type = takewhile(lambda ev: ev.type == cls.events_wave[0].type, cls.events_wave)
            return [ev.convert_to_sverchok_event() for ev in all_events_of_first_type]

    @classmethod
    def redraw_nodes(cls, sverchok_events: List[SverchokEvent]):
        for sv_event in sverchok_events:
            if cls.is_in_debug_mode():
                sv_event.print()
            sv_event.redraw_node()

    @staticmethod
    def update_nodes(sverchok_events: List[SverchokEvent]):
        process_from_nodes([ev.node for ev in sverchok_events if ev.type != SverchokEventsTypes.free_node])

    @staticmethod
    def is_in_debug_mode():
        with sv_preferences() as prefs:
            return prefs.log_level == "DEBUG" and prefs.log_update_events
