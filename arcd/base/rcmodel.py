"""
This file is part of ARCD.

ARCD is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

ARCD is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with ARCD. If not, see <https://www.gnu.org/licenses/>.
"""
from openpathsampling.engines.snapshot import BaseSnapshot as OPSBaseSnapshot
from openpathsampling.engines.trajectory import Trajectory as OPSTrajectory
from abc import ABC, abstractmethod
import numpy as np
# TODO: logging :)
import logging


logger = logging.getLogger(__name__)


class RCModel(ABC):
    """
    All RCModels should subclass this.

    Subclasses (or users) can define a self.descriptor_transform function,
    which will be applied to descriptors before prediction by the model.
    This could e.g. be a OPS-CV to transform OPS trajectories to numpy arrays,
    such that you can call a model on trajectories directly.
    """
    # TODO: property for trainSet ordering? or leave transform to the specific
    #       implementations of models if necessary?
    def __init__(self, descriptor_transform=None):
        self.descriptor_transform = descriptor_transform
        self.expected_p = []
        self.expected_q = []

    @property
    @abstractmethod
    def n_out(self):
        # returns the number of model outputs
        # need to know if we use binomial or multinomial
        pass

    @abstractmethod
    # TODO: save model in a file with name derived from simulation storage name?
    def save(self, fname):
        pass

    @abstractmethod
    # TODO: try to load model from file
    def load(self, fname):
        pass

    @abstractmethod
    def train_hook(self, trainset):
        # this will be called by the OPS training hook after every step
        # TODO: do we even need a seperate history that is passed here every time?
        pass

    @abstractmethod
    def _log_prob(self, descriptors):
        # returns the unnormalized log probabilities for given descriptors
        # descriptors is a numpy array with shape (n_points, n_descriptors)
        # the output is expected to be an array of shape (n_points, n_out)
        pass

    def train_expected_efficiency_factor(self, trainset, window):
        """
        Calculates (1 - {n_TP}_true / {n_TP}_expected)**2
        {n_TP}_true is summed over the last window entries of the trainset transitions
        {n_TP}_expected is calculated from self.expected_p assuming 2 independent shots
        """
        # make sure there are enough points, otherwise take less
        # TODO: or should we return 1. in that case?
        n_points = min(len(trainset), len(self.expected_p), window)
        n_tp_true = sum(trainset.transitions[-n_points:])
        p_ex = np.asarray(self.expected_p[-n_points:])
        if self.n_out == 1:
            n_tp_ex = np.sum(2 * (1 - p_ex[:, 0]) * p_ex[:, 0])
        else:
            n_tp_ex = 2 * np.sum([p_ex[:, i] * p_ex[:, j]
                                  for i in range(self.n_out)
                                  for j in range(i + 1, self.n_out)
                                  ])
        factor = (1 - n_tp_true / n_tp_ex)**2
        logger.info('Calculcated expected efficiency factor {:.3e} over {:d} points.'.format(factor, n_points))
        return factor

    # this will be called by selector after selecting a SP
    # TODO: do we need this? where else to put the storing of current prediction for SP?
    def register_sp(self, shoot_snap):
        self.expected_q.append(self.q(shoot_snap)[0])
        self.expected_p.append(self(shoot_snap)[0])

    def _apply_descriptor_transform(self, descriptors):
        # apply descriptor_transform if wanted and defined
        # returns either unaltered descriptors or transformed descriptors
        if self.descriptor_transform:
            # transform OPS snapshots to trajectories to get 2d arrays
            if isinstance(descriptors, OPSBaseSnapshot):
                descriptors = OPSTrajectory([descriptors])
            descriptors = self.descriptor_transform(descriptors)
        return descriptors

    def log_prob(self, descriptors, use_transform=True):
        """
        Return the unnormalized log probabilities for given descriptors.
        For n_out=1 only the log probability to reach state B is returned.
        """
        # if self.descriptor_transform is defined we use it before prediction
        # otherwise we just apply the model to descriptors
        if use_transform:
            descriptors = self._apply_descriptor_transform(descriptors)
        return self._log_prob(descriptors)

    def q(self, descriptors, use_transform=True):
        """
        Returns the reaction coordinate value(s) for given descriptors.
        For n_out=1 the RC towards state B is returned,
        otherwise the RC towards the state is returned for each state.
        """
        if self.n_out == 1:
            return self.log_prob(descriptors, use_transform)
        else:
            log_prob = self.log_prob(descriptors, use_transform)
            rc = [(log_prob[..., i:i+1]
                   - np.log(np.sum(np.exp(np.delete(log_prob, [i], axis=-1)), axis=-1, keepdims=True))
                   ) for i in range(log_prob.shape[-1])]
            return np.concatenate(rc, axis=-1)

    def __call__(self, descriptors, use_transform=True):
        """
        Returns p_B if n_out=1,
        otherwise the committment probabilities towards the states.
        """
        if self.n_out == 1:
            return self._p_binom(descriptors, use_transform)
        return self._p_multinom(descriptors, use_transform)

    def _p_binom(self, descriptors, use_transform):
        q = self.q(descriptors, use_transform)
        return 1/(1 + np.exp(-q))

    def _p_multinom(self, descriptors, use_transform):
        exp_log_p = np.exp(self.log_prob(descriptors, use_transform))
        return exp_log_p / np.sum(exp_log_p, axis=1)

    def z_sel(self, descriptors, use_transform=True):
        """
        Returns the value of the selection coordinate,
        which is zero at the most optimal point conceivable.
        For n_out=1 this is simply the unnormalized log probability.
        """
        if self.n_out == 1:
            return self.q(descriptors, use_transform)
        return self._z_sel_multinom(descriptors, use_transform)

    def _z_sel_multinom(self, descriptors, use_transform):
        """
        This expression is zero if (and only if) x is at the point of
        maximaly conceivable p(TP|x), i.e. all p_i are equal.
        z_{sel}(x) always lies in [0, 25], where z_{sel}(x)=25 implies
        p(TP|x)=0. We can therefore select the point for which this
        expression is closest to zero as the optimal SP.
        """
        p = self._p_multinom(descriptors, use_transform)
        # the prob to be on any TP is 1 - the prob to be on no TP
        # to be on no TP means beeing on a "self transition" (A->A, etc.)
        reactive_prob = 1 - np.sum(p * p, axis=1)
        # TODO: this should not be hardcoded....
        # scale z_sel to [0, 25]
        return (
                (25 / (1 - 1 / self.n_out))
                * (1 - 1 / self.n_out - reactive_prob)
                )
