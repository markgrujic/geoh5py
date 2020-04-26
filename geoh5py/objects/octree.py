import uuid
from typing import Optional, Tuple

import numpy as np

from ..data import FloatData
from .object_base import ObjectBase, ObjectType


class Octree(ObjectBase):
    """
    Octree mesh class that uses a tree structure where cells
    can be subdivided it into eight octants.

    The basic requirements needed to create an Octree mesh are:
        u, v, and w_count = Number of cells (power of 2) along each axis
        u, v, and w_cell_size = Cell size along each axis
    """

    __TYPE_UID = uuid.UUID(
        fields=(0x4EA87376, 0x3ECE, 0x438B, 0xBF, 0x12, 0x3479733DED46)
    )

    _attribute_map = ObjectBase._attribute_map.copy()
    _attribute_map.update(
        {
            "NU": "u_count",
            "NV": "v_count",
            "NW": "w_count",
            "Origin": "origin",
            "Rotation": "rotation",
            "U Cell Size": "u_cell_size",
            "V Cell Size": "v_cell_size",
            "W Cell Size": "w_cell_size",
        }
    )

    def __init__(self, object_type: ObjectType, **kwargs):

        self._origin = [0, 0, 0]
        self._rotation = 0.0
        self._u_count = None
        self._v_count = None
        self._w_count = None
        self._u_cell_size = None
        self._v_cell_size = None
        self._w_cell_size = None
        self._octree_cells = None
        self._centroids = None
        super().__init__(object_type, **kwargs)

        if object_type.name == "None":
            self.entity_type.name = "Octree"

        # if object_type.description is None:
        #     self.entity_type.description = "Octree"

        object_type.workspace._register_object(self)

    @classmethod
    def default_type_uid(cls) -> uuid.UUID:
        return cls.__TYPE_UID

    @property
    def origin(self):
        """
        Coordinates of the origin: array of floats, shape (3,)
        """
        return self._origin

    @origin.setter
    def origin(self, value):
        if value is not None:
            if isinstance(value, np.ndarray):
                value = value.tolist()

            assert len(value) == 3, "Origin must be a list or numpy array of shape (3,)"

            self.modified_attributes = "attributes"
            self._centroids = None

            value = np.asarray(
                tuple(value), dtype=[("x", float), ("y", float), ("z", float)]
            )
            self._origin = value

    @property
    def rotation(self) -> float:
        """
        Clockwise rotation angle (degree) about the vertical axis
        """
        return self._rotation

    @rotation.setter
    def rotation(self, value):
        if value is not None:
            value = np.r_[value]
            assert len(value) == 1, "Rotation angle must be a float of shape (1,)"
            self.modified_attributes = "attributes"
            self._centroids = None

            self._rotation = value.astype(float)

    @property
    def u_count(self) -> Optional[int]:
        """
        Number of base cells along u-axis
        """
        return self._u_count

    @u_count.setter
    def u_count(self, value):
        if value is not None:
            value = np.r_[value]
            assert len(value) == 1, "u_count must be type(int) of shape (1,)"
            self.modified_attributes = "attributes"
            self._centroids = None

            self._u_count = int(value)

    @property
    def v_count(self) -> Optional[int]:
        """
        Number of base cells along v-axis
        """
        return self._v_count

    @v_count.setter
    def v_count(self, value):
        if value is not None:
            value = np.r_[value]
            assert len(value) == 1, "v_count must be type(int) of shape (1,)"
            self.modified_attributes = "attributes"
            self._centroids = None

            self._v_count = int(value)

    @property
    def w_count(self) -> Optional[int]:
        """
        Number of base cells along w-axis
        """
        return self._w_count

    @w_count.setter
    def w_count(self, value):
        if value is not None:
            value = np.r_[value]
            assert len(value) == 1, "w_count must be type(int) of shape (1,)"
            self.modified_attributes = "attributes"
            self._centroids = None

            self._w_count = int(value)

    @property
    def u_cell_size(self) -> Optional[float]:
        """
        Base cell size along the u-coordinate
        """
        return self._u_cell_size

    @u_cell_size.setter
    def u_cell_size(self, value):
        if value is not None:
            value = np.r_[value]
            assert len(value) == 1, "u_cell_size must be type(float) of shape (1,)"
            self.modified_attributes = "attributes"
            self._centroids = None

            self._u_cell_size = value.astype(float)

    @property
    def v_cell_size(self) -> Optional[float]:
        """
        Base cell size along the v-coordinate
        """
        return self._v_cell_size

    @v_cell_size.setter
    def v_cell_size(self, value):
        if value is not None:
            value = np.r_[value]
            assert len(value) == 1, "v_cell_size must be type(float) of shape (1,)"
            self.modified_attributes = "attributes"
            self._centroids = None

            self._v_cell_size = value.astype(float)

    @property
    def w_cell_size(self) -> Optional[float]:
        """
        Base cell size along the w-coordinate
        """
        return self._w_cell_size

    @w_cell_size.setter
    def w_cell_size(self, value):
        if value is not None:
            value = np.r_[value]
            assert len(value) == 1, "w_cell_size must be type(float) of shape (1,)"
            self.modified_attributes = "attributes"
            self._centroids = None

            self._w_cell_size = value.astype(float)

    @property
    def octree_cells(self) -> Optional[np.ndarray]:
        """
        Array defining the i,j,k ordering and cell dimensions
            [i, j, k, n_cells]

        :return octree_cells: numpy.ndarray(int) of shape (nC, 4)

        """
        if getattr(self, "_octree_cells", None) is None:
            if self.existing_h5_entity:
                octree_cells = self.workspace.fetch_octree_cells(self.uid)
                self._octree_cells = octree_cells

            else:
                self.base_refine()

        return self._octree_cells

    @octree_cells.setter
    def octree_cells(self, value):
        if value is not None:
            value = np.vstack(value)

            assert (
                value.shape[1] == 4
            ), "'octree_cells' requires an ndarray of shape (*, 4)"
            self.modified_attributes = "octree_cells"
            self._centroids = None

            self._octree_cells = np.core.records.fromarrays(
                value.T, names="I, J, K, NCells", formats="<i4, <i4, <i4, <i4"
            )

    @property
    def shape(self) -> Optional[Tuple]:
        """
        Number of base cells along the u, v and w-axis
        """
        if (
            self.u_count is not None
            and self.v_count is not None
            and self.w_count is not None
        ):
            return self.u_count, self.v_count, self.w_count
        return None

    @property
    def centroids(self):
        """
        Coordinate locations of each cell centers [[x_i, y_i, z_i], ...]

        :return centroids: array of floats, shape(nC, 3)
        """
        if getattr(self, "_centroids", None) is None:
            assert self.octree_cells is not None, "octree_cells must be set"
            assert self.u_cell_size is not None, "u_cell_size must be set"
            assert self.v_cell_size is not None, "v_cell_size must be set"
            assert self.w_cell_size is not None, "w_cell_size must be set"

            angle = np.deg2rad(self.rotation)
            rot = np.r_[
                np.c_[np.cos(angle), -np.sin(angle), 0],
                np.c_[np.sin(angle), np.cos(angle), 0],
                np.c_[0, 0, 1],
            ]

            u_grid = (
                self.octree_cells["I"] + self.octree_cells["NCells"] / 2.0
            ) * self.u_cell_size
            v_grid = (
                self.octree_cells["J"] + self.octree_cells["NCells"] / 2.0
            ) * self.v_cell_size
            w_grid = (
                self.octree_cells["K"] + self.octree_cells["NCells"] / 2.0
            ) * self.w_cell_size

            xyz = np.c_[u_grid, v_grid, w_grid]

            self._centroids = np.dot(rot, xyz.T).T

            for ind, axis in enumerate(["x", "y", "z"]):
                self._centroids[:, ind] += self.origin[axis]

        return self._centroids

    @property
    def n_cells(self) -> Optional[int]:
        """
        Total number of cells in the mesh
        """
        if self.octree_cells is not None:
            return self.octree_cells.shape[0]
        return None

    def base_refine(self):
        """
        Refine the mesh to its base octree level resulting in a
        single cell along the shortest dimension.
        """
        assert (
            self._octree_cells is None
        ), "'base_refine' function only implemented if 'octree_cells' is None "

        # Number of octree levels allowed on each dimension
        level_u = np.log2(self.u_count)
        level_v = np.log2(self.v_count)
        level_w = np.log2(self.w_count)

        min_level = np.min([level_u, level_v, level_w])

        # Check that the refine level doesn't exceed the shortest dimension
        level = np.min([0, min_level])

        # Number of additional break to account for variable dimensions
        add_u = int(level_u - min_level)
        add_v = int(level_v - min_level)
        add_w = int(level_w - min_level)

        j, k, i = np.meshgrid(
            np.arange(0, self.v_count, 2 ** (level_v - add_v - level)),
            np.arange(0, self.w_count, 2 ** (level_w - add_w - level)),
            np.arange(0, self.u_count, 2 ** (level_u - add_u - level)),
        )

        octree_cells = np.c_[
            i.flatten(),
            j.flatten(),
            k.flatten(),
            np.ones_like(i.flatten()) * 2 ** (min_level - level),
        ]

        self._octree_cells = np.rec.fromarrays(
            octree_cells.T,
            names=["I", "J", "K", "NCells"],
            formats=["<i4", "<i4", "<i4", "<i4"],
        )
