from __future__ import annotations

import uuid
import weakref
from contextlib import contextmanager
from typing import (
    TYPE_CHECKING,
    Callable,
    ClassVar,
    Dict,
    Iterable,
    List,
    Optional,
    Type,
    Union,
    cast,
)

from .root_group import RootGroup

if TYPE_CHECKING:
    from geoh5io.groups import group
    from geoh5io.objects import object_base
    from geoh5io.data import data
    from geoh5io.shared import entity_type


WeakRefDuckType = Union[weakref.ReferenceType, Callable[[], Optional["Workspace"]]]


class Workspace:

    _active_ref: ClassVar[WeakRefDuckType] = type(None)

    def __init__(self, root: RootGroup = None):
        self.version = None
        self._distance_unit = None
        self._contributors: List[str] = []

        # TODO: use weak ref dict
        self._types: Dict[uuid.UUID, entity_type.EntityType] = {}
        self._groups: Dict[uuid.UUID, group.Group] = {}
        self._objects: Dict[uuid.UUID, object_base.ObjectBase] = {}
        self._data: Dict[uuid.UUID, data.Data] = {}

        self._root = root if root is not None else RootGroup(self)

    @property
    def root(self) -> "group.Group":
        return self._root

    def activate(self):
        """ Makes this workspace the active one.

            In case the workspace gets deleted, Workspace.active() safely returns None.
        """
        if Workspace._active_ref() is not self:
            Workspace._active_ref = weakref.ref(self)

    def deactivate(self):
        """ Deactivate this workspace if it was the active one, else does nothing.
        """
        if Workspace._active_ref() is self:
            Workspace._active_ref = type(None)

    @staticmethod
    def active() -> Workspace:
        """ Get the active workspace. """
        active_one = Workspace._active_ref()
        if active_one is None:
            raise RuntimeError("No active workspace.")

        # so that type check does not complain of possible returned None
        return cast(Workspace, active_one)

    def register_type(self, entity_type: "entity_type.EntityType"):
        # TODO: raise exception if it does already exists
        self._types[entity_type.uid] = entity_type

    def find_type(
        self, type_uid: uuid.UUID, type_class: Type["entity_type.EntityType"]
    ) -> Optional["entity_type.EntityType"]:
        found_type = self._types.get(type_uid, None)
        if found_type is not None and isinstance(found_type, type_class):
            return found_type

        return None

    def all_groups(self) -> Iterable["group.Group"]:
        return self._groups.values()

    def find_group(self, group_uid: uuid.UUID) -> Optional["group.Group"]:
        return self._groups.get(group_uid, None)

    def all_objects(self) -> Iterable["object_base.ObjectBase"]:
        return self._objects.values()

    def find_object(self, object_uid: uuid.UUID) -> Optional["object_base.ObjectBase"]:
        return self._objects.get(object_uid, None)

    def all_data(self) -> Iterable["data.Data"]:
        return self._data.values()

    def find_data(self, data_uid: uuid.UUID) -> Optional["data.Data"]:
        return self._data.get(data_uid, None)


@contextmanager
def active_workspace(workspace: Workspace):
    previous_active_ref = Workspace._active_ref  # pylint: disable=protected-access
    workspace.activate()
    yield workspace

    workspace.deactivate()
    # restore previous active workspace when leaving the context
    previous_active = previous_active_ref()
    if previous_active is not None:
        previous_active.activate()  # pylint: disable=no-member
