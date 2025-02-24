#  Copyright (c) 2021 Mira Geoscience Ltd.
#
#  This file is part of geoh5py.
#
#  geoh5py is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Lesser General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  geoh5py is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with geoh5py.  If not, see <https://www.gnu.org/licenses/>.

import tempfile
from gc import collect
from pathlib import Path

import numpy as np

from geoh5py.groups import ContainerGroup
from geoh5py.objects import Curve
from geoh5py.workspace import Workspace


def test_delete_entities():

    xyz = np.random.randn(12, 3)
    values = np.random.randn(12)

    with tempfile.TemporaryDirectory() as tempdir:
        # Create a workspace
        workspace = Workspace(str(Path(tempdir) / r"testPoints.geoh5"))

        group = ContainerGroup.create(workspace)
        curve_1 = Curve.create(workspace, vertices=xyz, parent=group)
        curve_1.add_data({"DataValues": {"association": "VERTEX", "values": values}})

        # Create second object with data sharing type
        curve_2 = Curve.create(workspace, vertices=xyz, parent=group)

        # Add data
        for i in range(4):
            values = np.random.randn(curve_2.n_vertices)
            if i == 0:  # Share the data type
                curve_2.add_data(
                    {
                        f"Period{i + 1}": {
                            "values": values,
                            "entity_type": curve_1.children[0].entity_type,
                        }
                    },
                    property_group="myGroup",
                )
            else:
                curve_2.add_data(
                    {f"Period{i + 1}": {"values": values}}, property_group="myGroup"
                )
        uid_out = curve_2.children[1].uid

        workspace.remove_entity(curve_2.children[0])
        workspace.remove_entity(curve_2.children[0])

        assert (
            uid_out
            not in curve_2.find_or_create_property_group(name="myGroup").properties
        ), "Data uid was not removed from the property_group"
        assert (
            len(workspace.data) == 3
        ), "Data were not fully removed from the workspace."
        assert (
            len(curve_2.children) == 2
        ), "Data were not fully removed from the parent object."
        assert (
            len(workspace.types) == 6
        ), "Data types were not properly removed from the workspace."

        # Remove entire object with data
        workspace.remove_entity(curve_2)

        del curve_2  # Needed since still referenced in current script
        collect()
        assert (
            len(workspace.groups) == 2
        ), "Group was not fully removed from the workspace."
        assert (
            len(workspace.objects) == 1
        ), "Object was not fully removed from the workspace."
        assert (
            len(workspace.data) == 1
        ), "Data were not properly removed from the workspace."
        assert (
            len(workspace.types) == 4
        ), "Data types were not properly removed from the workspace."

        # Re-open the project and check all was removed
        workspace = Workspace(str(Path(tempdir) / r"testPoints.geoh5"))
        assert (
            len(workspace.groups) == 2
        ), "Groups were not properly written to the workspace."
        assert (
            len(workspace.objects) == 1
        ), "Objects were not properly written to the workspace."
        assert (
            len(workspace.data) == 1
        ), "Data were not properly written to the workspace."
        assert (
            len(workspace.types) == 4
        ), "Types were not properly written to the workspace."
