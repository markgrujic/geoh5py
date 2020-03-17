from SimPEG import Mesh, Maps, Utils
import numpy as np
import scipy as sp
from scipy.spatial import cKDTree

from simpegEM1D import (
    GlobalEM1DProblemFD, GlobalEM1DSurveyFD,
    get_vertical_discretization_frequency,
    get_2d_mesh, LateralConstraint, set_mesh_1d,
    EM1D
)

from pymatsolver import PardisoSolver
from SimPEG import (
    Regularization, Directives, Inversion, InvProblem, Optimization, DataMisfit, Utils
)
import multiprocessing
from scipy.constants import mu_0
import os
import shutil
import sys

from geoh5io.workspace import Workspace
from geoh5io.objects import Grid2D, Curve, Points, Surface
from geoh5io.data import Data
from geoh5io.groups import ContainerGroup
import json

import matplotlib.tri as mtri
from scipy.spatial import Delaunay

class SaveIterationsGeoH5(Directives.InversionDirective):
    """
        Saves inversion results to a geoh5 file
    """
    # Initialize the output dict
    h5_object = None
    channels = ['model']
    attribute = "model"
    association = "VERTEX"
    sorting = None
    mapping = None

    def initialize(self):
        if self.attribute == "model":
            prop = self.invProb.model

        elif self.attribute == "predicted":
            return

        if self.mapping is not None:
            prop = self.mapping * prop

        for ii, channel in enumerate(self.channels):

            attr = prop[ii::len(self.channels)]

            if self.sorting is not None:
                attr = attr[self.sorting]

            data = self.h5_object.add_data({
                    f"Initial": {
                        "association":self.association, "values": attr
                    }
                }
            )

            if self.attribute == "predicted":
                self.h5_object.add_data_to_group(data, f"Initial")

        self.h5_object.workspace.finalize()

    def endIter(self):

        if self.attribute == "model":
            prop = self.invProb.model

        elif self.attribute == "predicted":
            prop = self.invProb.dpred

        if self.mapping is not None:
            prop = self.mapping * prop

        for ii, channel in enumerate(self.channels):

            attr = prop[ii::len(self.channels)]

            if self.sorting is not None:
                attr = attr[self.sorting]

            data = self.h5_object.add_data({
                    f"Iteration_{self.opt.iter}_" + channel: {
                        "association":self.association, "values": attr
                    }
                }
            )

            if self.attribute == "predicted":
                self.h5_object.add_data_to_group(data, f"Iteration_{self.opt.iter}")

        self.h5_object.workspace.finalize()


def inversion(argv):
    """

    """
    dsep = os.path.sep
    input_file = sys.argv[1]

    with open(input_file, 'r') as f:
        input_param = json.load(f)

    with open("functions/AEM_systems.json", 'r') as f:
        fem_specs = json.load(f)[input_param['system']]

    nThread = int(multiprocessing.cpu_count()/2)
    lower_bound = 1e-5
    upper_bound = 100
    chi_target = input_param['chi_factor'][0]
    workspace = Workspace(input_param['workspace'])
    entity = workspace.get_entity(input_param['entity'])[0]
    selection = input_param['lines']
    downsampling = np.float(input_param['downsampling'])

    locations = entity.vertices
    dem = entity.get_data(input_param['topo'])[0].values

    frequencies = []
    for channel, freq in fem_specs['channels'].items():
        if channel in list(input_param['data'].keys()):

            frequencies.append(freq)

    frequencies = np.unique(np.hstack(frequencies))
    nF = len(frequencies)

    channels = [
        channel for channel, freq in fem_specs['channels'].items() if freq in frequencies
    ]

    hz = np.ones(20)*5*np.exp(np.arange(0, 20)*.115)
    CCz = -np.cumsum(hz) + hz/2.
    nZ = hz.shape[0]

    # Select data and downsample
    stn_id = []
    model_count = 0
    model_ordering = []
    model_vertices = []
    model_cells = []
    pred_count = 0
    data_ordering = []
    pred_vertices = []
    pred_cells = []

    for key, values in selection.items():

        for line in values:

            line_ind = np.where(entity.get_data(key)[0].values == np.float(line))[0]

            xyz = locations[line_ind, :]
            nstn = xyz.shape[0]
            keep = np.ones(nstn, dtype='bool')
            if downsampling > 0:

                # locations = entity.vertices
                xx = np.arange(xyz[:, 0].min()-downsampling, xyz[:, 0].max()+downsampling, downsampling)
                yy = np.arange(xyz[:, 1].min()-downsampling, xyz[:, 1].max()+downsampling, downsampling)

                X, Y = np.meshgrid(xx, yy)

                tree = cKDTree(xyz[:, :2])
                rad, ind = tree.query(np.c_[X.ravel(), Y.ravel()])
                keep = np.unique(ind[rad < downsampling])

                line_ind = line_ind[keep]

            stn_id.append(line_ind)

            n_sounding = len(line_ind)
            if n_sounding < 2:
                continue

            xyz = locations[line_ind, :]
            # Create a 2D mesh to store the results
            if np.std(xyz[:, 1]) > np.std(xyz[:, 0]):
                order = np.argsort(xyz[:, 1])
            else:
                order = np.argsort(xyz[:, 0])

            x_loc = xyz[:, 0][order]
            y_loc = xyz[:, 1][order]
            z_loc = dem[line_ind][order]

            # Create a grid for the surface
            X = np.kron(np.ones(nZ), x_loc.reshape((x_loc.shape[0], 1)))
            Y = np.kron(np.ones(nZ), y_loc.reshape((x_loc.shape[0], 1)))
            Z = np.kron(np.ones(nZ), z_loc.reshape((x_loc.shape[0], 1))) + np.kron(CCz, np.ones((x_loc.shape[0],1)))

            if np.std(y_loc) > np.std(x_loc):
                tri2D = Delaunay(np.c_[np.ravel(Y), np.ravel(Z)])

            else:
                tri2D = Delaunay(np.c_[np.ravel(X), np.ravel(Z)])

            max_length = 1000
            indx = np.ones(tri2D.simplices.shape[0], dtype=bool)
            for ii in range(3):

                indx *= np.linalg.norm(
                    tri2D.points[tri2D.simplices[:, ii]] -
                    tri2D.points[tri2D.simplices[:, ii-1]],
                    axis=1
                ) < max_length

            # Remove the simplices too long
            tri2D.simplices = tri2D.simplices[indx, :]
            tri2D.vertices = tri2D.vertices[indx, :]

            temp = np.arange(int(nZ * n_sounding)).reshape((nZ, n_sounding), order='F')
            model_ordering.append(temp[:, order].T.ravel() + model_count)
            model_vertices.append(np.c_[np.ravel(X), np.ravel(Y), np.ravel(Z)])
            model_cells.append(tri2D.simplices+model_count)

            data_ordering.append(order + pred_count)

            pred_vertices.append(xyz[order, :])
            pred_cells.append(np.c_[np.arange(x_loc.shape[0]-1), np.arange(x_loc.shape[0]-1)+1] + pred_count)

            model_count += tri2D.points.shape[0]
            pred_count += x_loc.shape[0]

        out_group = ContainerGroup.create(
            workspace,
            name=input_param['out_group']
            )

        surface = Surface.create(
            workspace,
            name=f"Model_Sections",
            vertices=np.vstack(model_vertices),
            cells=np.vstack(model_cells),
            parent=out_group
        )
        model_ordering = np.hstack(model_ordering).astype(int)
        curve = Curve.create(
            workspace,
            name=f"Predicted",
            vertices=np.vstack(pred_vertices),
            cells=np.vstack(pred_cells).astype("uint32"),
            parent=out_group
        )
        data_ordering = np.hstack(data_ordering)

    reference = 'BFHS'
    if input_param['reference']:

        if isinstance(input_param['reference'], str):

            con_object = workspace.get_entity(input_param['reference'])[0]
            con_model = con_object.values

            grid = con_object.parent.centroids

            tree = cKDTree(grid)
            _, ind = tree.query(np.vstack(model_vertices))

            ref = con_model[ind]
            reference = np.log(ref[np.argsort(model_ordering)])

        elif isinstance(input_param['reference'], float):

            reference = np.ones(np.vstack(model_vertices).shape[0]) * np.log(input_param['reference'])

    stn_id = np.hstack(stn_id)

    n_sounding = stn_id.shape[0]

    dobs = np.zeros(n_sounding * 2 * nF)
    uncert = np.zeros(n_sounding * 2 * nF)
    offset = {}

    nD = 0

    for ind, channel in enumerate(channels):

        if channel in list(input_param['data'].keys()):

            pc_floor = np.asarray(input_param['uncert']["channels"][channel]).astype(float)

            dobs[ind::nF*2] = entity.get_data(input_param['data'][channel])[0].values[stn_id]
            uncert[ind::nF*2] = dobs[ind::nF*2] * pc_floor[0] + pc_floor[1] * (1-pc_floor[0])

            nD += dobs[ind::nF*2].shape[0]

            offset[str(fem_specs['channels'][channel])] = np.linalg.norm(
                np.asarray(input_param["rx_offsets"][channel]).astype(float))

    offset = list(offset.values())
    uncert[dobs <= 0] = np.inf

    ind = 0
    for ind, channel in enumerate(channels):
        if channel in list(input_param['data'].keys()):
            d_i = curve.add_data({
                    input_param['data'][channel]: {
                        "association": "VERTEX", "values": dobs[ind::(nF*2)][data_ordering]
                    }
            })

            curve.add_data_to_group(d_i, f"Observed")

    freq = np.kron(np.ones(2), np.kron(np.ones(n_sounding), frequencies))

    xyz = entity.vertices[stn_id, :]
    ztopo = dem[stn_id]
    topo = np.c_[xyz[:, :2], ztopo]

    survey = GlobalEM1DSurveyFD(
            rx_locations=xyz,
            src_locations=xyz,
            frequency=frequencies.astype(float),
            offset=np.r_[offset],
            src_type=fem_specs['tx_specs']['type'],
            rx_type=fem_specs['normalization'],
            a=fem_specs['tx_specs']['a'],
            I=fem_specs['tx_specs']['I'],
            field_type='secondary',
            topo=topo,
        )

    survey.dobs = dobs

    if reference is "BFHS" or input_param['uncert']['mode'] == 'Estimated (%|data| + background)':
        print("**** Best-fitting halfspace inversion ****")
        print(f"Target: {nD}")
        mesh1D = Mesh.TensorMesh([1], [0.])
        sig_half = 1e-3

        hz_BFHS = np.r_[1.]
        mapping = Maps.ExpMap(nP=n_sounding)
        expmap = Maps.ExpMap(nP=n_sounding)
        # expmap_h = Maps.ExpMap(nP=1)
        sigmaMap = expmap

        # sub_sample = np.arange((len(frequencies)-1), dobs.shape[0], len(frequencies)*2)
        # sub_sample = np.sort(np.r_[sub_sample, np.arange((len(frequencies)*2-1), dobs.shape[0], len(frequencies)*2)])
        # print(sub_sample)
        surveyHS = GlobalEM1DSurveyFD(
            rx_locations=xyz,
            src_locations=xyz,
            frequency=frequencies.astype(float),
            offset=np.r_[offset],
            src_type=fem_specs['tx_specs']['type'],
            a=fem_specs['tx_specs']['a'],
            I=fem_specs['tx_specs']['I'],
            rx_type=fem_specs['normalization'],
            field_type='secondary',
            topo=topo,
            half_switch=True
        )

        surveyHS.dobs = dobs#[sub_sample]
        probHalfspace = GlobalEM1DProblemFD(
            [], sigmaMap=sigmaMap, hz=hz_BFHS,
            parallel=True, n_cpu=nThread,
            verbose=False,
            Solver=PardisoSolver
        )

        probHalfspace.pair(surveyHS)

        dmisfit = DataMisfit.l2_DataMisfit(surveyHS)

        # Real part only
        # uncert_inphase = uncert.copy()
        # for ind in range(nF):
        #     uncert_inphase[ind+nF::nF*2] = np.inf

        dmisfit.W = 1./uncert#[sub_sample]
        m0 = np.log(np.ones(n_sounding)*sig_half)
        # e = np.ones(n_sounding)

        d0 = surveyHS.dpred(m0)
        mesh_reg = get_2d_mesh(n_sounding, np.r_[1])
        # mapping is required ... for IRLS
        regmap = Maps.IdentityMap(mesh_reg)
        reg_sigma = LateralConstraint(
                    mesh_reg, mapping=regmap,
                    alpha_s=1.,
                    alpha_x=1.,
                    alpha_y=1.,
        )

        min_distance = None
        if downsampling > 0:
            min_distance = downsampling * 4

        reg_sigma.get_grad_horizontal(
            xyz[:, :2] + np.random.randn(xyz.shape[0], 2), hz_BFHS, dim=2,
            minimum_distance=min_distance
        )

        IRLS = Directives.Update_IRLS(
            maxIRLSiter=0, minGNiter=1, fix_Jmatrix=True, betaSearch=False,
            chifact_start=chi_target*5, chifact_target=chi_target*5
        )
        # opt = Optimization.InexactGaussNewton(maxIter=10)
        opt = Optimization.ProjectedGNCG(
            maxIter=5, lower=np.log(lower_bound),
            upper=np.log(upper_bound), maxIterLS=20,
            maxIterCG=50, tolCG=1e-5
        )
        invProb_HS = InvProblem.BaseInvProblem(dmisfit, reg_sigma, opt)
        beta = Directives.BetaSchedule(coolingFactor=2, coolingRate=1)
        target = Directives.TargetMisfit()
        betaest = Directives.BetaEstimate_ByEig(beta0_ratio=10.)
        update_Jacobi = Directives.UpdatePreconditioner()
        inv = Inversion.BaseInversion(
            invProb_HS, directiveList=[betaest, IRLS, update_Jacobi]
        )

        opt.LSshorten = 0.5
        opt.remember('xc')
        mopt = inv.run(m0)
        # Return predicted of Best-fitting halfspaces

    if reference is "BFHS":
        m0 = Utils.mkvc(np.kron(mopt, np.ones_like(hz)))
        mref = m0
    else:
        m0 = reference
        mref = m0

    mapping = Maps.ExpMap(nP=int(n_sounding*hz.size))
    mesh_reg = get_2d_mesh(n_sounding, hz)

    if survey.ispaired:
        survey.unpair()

    prob = GlobalEM1DProblemFD(
        [], sigmaMap=mapping, hz=hz, parallel=True, n_cpu=nThread,
        Solver=PardisoSolver
    )
    prob.pair(survey)

    pred = survey.dpred(m0)

    for ind, channel in enumerate(channels):

        d_i = curve.add_data({
                "Iteration_0_" + channel: {
                    "association": "VERTEX", "values": pred[ind::(nF*2)][data_ordering]
                }
        })

        curve.add_data_to_group(d_i, f"Iteration_0")

    # Write uncertities to objects
    for ind, channel in enumerate(channels):

        if channel in list(input_param['data'].keys()):

            pc_floor = np.asarray(input_param['uncert']["channels"][channel]).astype(float)

            if input_param['uncert']['mode'] == 'Estimated (%|data| + background)':

                uncert[ind::(nF*2)] = dobs[ind::nF*2] * pc_floor[0] + np.median(pred[ind::(nF*2)]) * (1-pc_floor[0])

            d_i = curve.add_data({
                "Uncertainties_" + channel: {
                    "association": "VERTEX", "values": uncert[ind::(nF*2)][data_ordering]
                }
            })

            curve.add_data_to_group(d_i, f"Uncertainties")

        uncert[dobs <= 0] = np.inf

    mesh_reg = get_2d_mesh(n_sounding, hz)
    dmisfit = DataMisfit.l2_DataMisfit(survey)
    dmisfit.W = 1./uncert

    regmap = Maps.IdentityMap(mesh_reg)

    reg = LateralConstraint(
        mesh_reg, mapping=Maps.IdentityMap(nP=mesh_reg.nC),
        alpha_s=1.,
        alpha_x=1.,
        alpha_y=1.,
        gradientType='total'
    )

    wr = prob.getJtJdiag(m0)**0.5
    wr /= wr.max()

    surface.add_data({"Cell_weights": {"values": wr[model_ordering]}})

    min_distance = None
    if downsampling > 0:
        min_distance = downsampling * 4

    tri = reg.get_grad_horizontal(
        xyz[:, :2] + np.random.randn(xyz.shape[0], 2), hz,
        minimum_distance=min_distance
    )
    p = 2
    qx, qz = 0., 0.
    reg.norms = np.c_[p, qx, qz, 0.]
    # reg.cell_weights = wr
    # reg.mref = mref
    opt = Optimization.ProjectedGNCG(
        maxIter=15, lower=np.log(lower_bound),
        upper=np.log(upper_bound), maxIterLS=20,
        maxIterCG=50, tolCG=1e-5
    )

    invProb = InvProblem.BaseInvProblem(dmisfit, reg, opt)

    # beta = Directives.BetaSchedule(coolingFactor=0.5, coolingRate=1)
    update_Jacobi = Directives.UpdatePreconditioner()
    saveDict = Directives.SaveOutputDictEveryIteration()
    sensW = Directives.UpdateSensitivityWeights()
    target = Directives.TargetMisfit()
    saveModel = SaveIterationsGeoH5(
        h5_object=surface, sorting=model_ordering,
        mapping=mapping, attribute="model"
    )

    savePred = SaveIterationsGeoH5(
        h5_object=curve, sorting=data_ordering,
        mapping=1, attribute="predicted",
        channels=channels
    )

    IRLS = Directives.Update_IRLS(
        maxIRLSiter=10, minGNiter=1, betaSearch=False, beta_tol=0.25,
        chifact_start=chi_target, chifact_target=chi_target,
    )

    betaest = Directives.BetaEstimate_ByEig(beta0_ratio=1.)
    inv = Inversion.BaseInversion(
        invProb, directiveList=[
            saveModel, savePred, sensW, IRLS, update_Jacobi, betaest
        ]
    )

    prob.counter = opt.counter = Utils.Counter()
    opt.LSshorten = 0.5
    opt.remember('xc')
    mopt = inv.run(m0)

if __name__ == '__main__':

    input_file = sys.argv[1]

    inversion(input_file)
