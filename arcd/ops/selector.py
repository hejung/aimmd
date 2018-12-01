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
import logging
import numpy as np
from openpathsampling.shooting import ShootingPointSelector
from ..data.history import History

logger = logging.getLogger(__name__)


class CommittorModelSelector(ShootingPointSelector):
    """
    Selects 'ideal' shooting points learned by the corresponding model,
    the points are ideal in the sense that p(TP|x) is maximal there.
    Can be used together with `CommittorModelTrainer`.

    Parameters
    ----------
    model - :class:`arcd.data.OPSWrapperBase` a wrapped model predicting RC values,
            should be the same object as for the corresponding CommittorModelTrainer,
    coords_cv - :class:`openpathsampling.CollectiveVariable` transforming
                (Cartesian) snapshot coordinates to the coordinate
                representation in which the model learns, see `.coordinates` for
                examples of functions that can be turned to a MDtrajFunctionCV
    states - TODO
    history - TODO
    distribution - string specifying the SP selection distribution,
                   either 'gaussian' or 'lorentzian'
                   'gaussian': p_{sel}(x) ~ exp(-alpha * z_{sel}(x)**2)
                   'lorentzian': p_{sel}(x) ~ gamma**2 / (gamma**2 + z_{sel}(x)**2)
    scale - float, 'sharpness' parameter of the selection distribution,
            higher values result in more sharp selections around the TSE,
            1/alpha for 'gaussian' and gamma for 'lorentzian'

    Notes
    -----
    We use the z_sel function of the model wrapper as input to the selection distribution.
    """
    def __init__(self, model, coords_cv, states, history=None,
                 distribution='lorentzian', scale=1.):
        super(CommittorModelSelector, self).__init__()
        if history:
            self.history = history
        else:
            self.history = History()
        self.model = model
        self.coords_cv = coords_cv
        self.states = states
        self.distribution = distribution
        self.scale = scale

    @classmethod
    def from_dict(cls, dct):
        # TODO: FIXME: atm we set model = None,
        # since we can not save keras models in OPS storages
        # we wrote this dirty hack that ANNTrainer saves the model after simulation
        # and tries to restore on begin of simulation from hdf5 files named
        # like the corresponding storage
        scale = dct['scale']
        distribution = dct['distribution']
        obj = cls(None, dct['coords_cv'],
                  dct['states'],
                  history=None,
                  distribution=distribution,
                  scale=scale)
        logger.warn('Restoring CommittorModelSelector without model.'
                    + ' Will try to restore it at the first step of TPS.')
        return obj

    def to_dict(self):
        dct = {}
        dct['coords_cv'] = self.coords_cv
        dct['distribution'] = self._distribution
        dct['scale'] = self.scale
        dct['states'] = self.states
        return dct

    @property
    def distribution(self):
        return self._distribution

    @distribution.setter
    def distribution(self, val):
        if val == 'gaussian':
            self._f_sel = lambda z: self._gaussian(z)
            self._distribution = val
        elif val == 'lorentzian':
            self._f_sel = lambda z: self._lorentzian(z)
            self._distribution = val
        else:
            raise ValueError('Distribution must be one of: '
                             + '"gaussian" or "lorentzian"')

    def _lorentzian(self, z):
        return self.scale / (self.scale**2 + z**2)

    def _gaussian(self, z):
        return np.exp(-z**2/self.scale)

    def f(self, snapshot, trajectory):
        '''
        Returns the unnormalized proposal probability of a snapshot

        Notes
        -----
        In principle this is an collectivevariable so we could easily add
        caching if useful
        '''
        # TODO: do we need to check if snapshot is in trajectory?
        z_sel = self.model.z_sel(snapshot)
        if not np.all(np.isfinite(z_sel)):
            logger.warn('The model predicts NaNs or infinities. '
                        + 'We used np.nan_to_num to proceed')
            z_sel = np.nan_to_num(z_sel)
        # casting to python float solves the problem that
        # metropolis_acceptance is not saved !
        ret = float(self._f_sel(z_sel))
        if ret == 0.:
            if self.sum_bias(trajectory) == 0.:
                return 1.
        return ret

    def probability(self, snapshot, trajectory):
        # only evaluate costly symmetry functions if needed,
        # if trajectory is no TP it has weight 0 and p_pick = 0 for all points
        self_transitions = [1 < sum([s(p)
                                     for p in [trajectory[0], trajectory[-1]]])
                            for s in self.states]
        if any(self_transitions):
            return 0.
        # trajectory is a TP, calculate p_pick
        sum_bias = self.sum_bias(trajectory)
        if sum_bias == 0.:
            return 1./len(trajectory)
        return self.f(snapshot, trajectory) / sum_bias

    def sum_bias(self, trajectory):
        # casting to python float solves the problem that
        # metropolis_acceptance is not saved !
        return float(np.sum(self._biases(trajectory)))

    def _biases(self, trajectory):
        z_sels = self.model.z_sel(trajectory)
        if not np.all(np.isfinite(z_sels)):
            logger.warn('The model predicts NaNs or infinities. '
                        + 'We used np.nan_to_num to proceed')
            z_sels = np.nan_to_num(z_sels)
        return self._f_sel(z_sels)

    def pick(self, trajectory):
        '''
        Returns the index of the chosen snapshot within `trajectory`
        '''
        biases = self._biases(trajectory)
        sum_bias = np.sum(biases)
        if sum_bias == 0.:
            logger.error('Model not able to give educated guess.\
                         Choosing based on luck.')
            # we can not give any meaningfull advice and choose at random
            return np.random.randint(len(trajectory))

        rand = np.random.random() * sum_bias
        idx = 0
        prob = biases[0]
        while prob <= rand and idx < len(biases):
            idx += 1
            prob += biases[idx]

        # store p(TP|x_pick) in the trainer
        # slice to preserve trajectory
        ps = self.model.p(trajectory[idx:idx + 1])
        if ps.shape[1] == 1:
            p_TP_pick = 2 * ps[0, 0] * (1. - ps[0, 0])
        else:
            p_TP_pick = 1. - np.sum(ps * ps)
        self.history.expected_efficiency.append(float(p_TP_pick))

        return idx
