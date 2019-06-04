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
from .trainset import TrainSet


def emulate_production_from_trainset(model, trainset):
    """
    Emulates a TPS production run from given trainset.

    This function retraces the exact same sequence of shooting points
    and generated trial transitions as the original TPS simulation.
    Very useful to quickly test different models/ model architectures
    on existing shooting data without costly trial trajectory propagation.

    NOTE: This can only be used to (re-)train on the same descriptors.

    Parameters
    ----------
        model - :class:`arcd.base.RCModel` the model to train
        trainset - :class:`arcd.TrainSet` trainset with shooting data

    Returns
    -------
        model - :class:`arcd.base.RCModel` the trained model

    """
    new_ts = TrainSet(states=trainset.states,
                      # actually we do not use the descriptor_transform
                      descriptor_transform=trainset.descriptor_transform)
    for i in range(len(trainset)):
        descriptors = trainset.descriptors[i:i+1]
        # register_sp expects 2d arrays (as the model always does)
        model.register_sp(descriptors, use_transform=False)
        # get the result,
        # in reality we would need to propagate two trial trajectories
        shot_result = trainset.shot_results[i]
        # append_point expects 1d arrays
        new_ts.append_point(descriptors[0], shot_result)
        # let the model decide if it wants to train
        model.train_hook(new_ts)

    return model


def emulate_production_from_storage(model, storage, states):
    """
    Emulates a TPS production run from given trainset.

    This function retraces the exact same sequence of shooting points
    and generated trial transitions as the original TPS simulation.
    Very useful to quickly test different models/ model architectures
    on existing shooting data without costly trial trajectory propagation.

    NOTE: This should only be used to (re-)train on different descriptors
          as it recalculates the potentially costly descriptor_transform
          for every shooting point.

    Parameters
    ----------
        model - :class:`arcd.base.RCModel` the model to train
        storage - :class:`openpathsampling.Storage` with simulation data
        states - list of :class:`openpathsampling.Volume` the (meta-)stable
                 states for the TPS simulation

    Returns
    -------
    model, trainset
    where:
        model - :class:`arcd.base.RCModel` the trained model
        trainset - :class:`arcd.TrainSet` the newly created trainset

    """
    new_ts = TrainSet(states=states,
                      # here we actually use the transform!
                      descriptor_transform=model.descriptor_transform)
    for step in storage.steps:
        try:
            # not every step has a shooting snapshot
            # e.g. the initial transition path does not
            # steps without shooting snap can not be trained on
            sp = step.change.canonical.details.shooting_snapshot
        except AttributeError:
            # no shooting snap
            continue
        except IndexError:
            # no trials!
            continue
        # let the model predict what it thinks
        model.register_sp(sp)
        # add to trainset
        new_ts.append_ops_mcstep(step)
        # (possibly) train
        model.train_hook(new_ts)

    return model, new_ts