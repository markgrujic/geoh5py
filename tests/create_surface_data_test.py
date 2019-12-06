import os

import numpy as np
from scipy.spatial import Delaunay

from geoh5io.objects import Surface
from geoh5io.workspace import Workspace


def test_create_surface_data():

    h5file = "testSurface_orig.geoh5"

    workspace = Workspace(os.getcwd() + os.sep + "assets" + os.sep + h5file)

    # Create a grid of points and triangulate
    x, y = np.meshgrid(np.arange(10), np.arange(10))
    x, y = x.ravel(), y.ravel()
    z = np.random.randn(x.shape[0])

    del_surf = Delaunay(np.c_[x, y])

    simplices = getattr(del_surf, "simplices")

    # Create random data
    values = np.mean(
        np.c_[x[simplices[:, 0]], x[simplices[:, 1]], x[simplices[:, 2]]], axis=1
    )

    # Create a geoh5 surface
    surface, data_object = Surface.create(
        workspace,
        name="mySurf",
        vertices=np.c_[x, y, z],
        cells=simplices,
        data={"TMI": ["CELL", values]},
    )

    workspace.save_entity(surface)
    workspace.finalize()

    # Write the object to a different workspace
    new_workspace = Workspace(
        os.getcwd() + os.sep + "assets" + os.sep + "testSurface.geoh5"
    )

    new_workspace.save_entity(surface)
    new_workspace.finalize()

    obj_copy = new_workspace.get_entity("mySurf")[0]
    data_copy = obj_copy.get_data("TMI")

    assert [
        prop in obj_copy.get_data_list for prop in surface.get_data_list
    ], "The surface object did not copy"
    assert np.all(data_copy.values == data_object.values), "Data values were not copied"
    os.remove(os.getcwd() + os.sep + "assets" + os.sep + "testSurface.geoh5")
    os.remove(os.getcwd() + os.sep + "assets" + os.sep + "testSurface_orig.geoh5")
