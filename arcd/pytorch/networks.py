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
import torch.nn as nn
import torch.nn.functional as F


# NOTE ON PYTORCH MODELS
# every ANN here needs to have a self.call_kwargs dictionary
# containing the kwargs needed to instantiate the ANN
# the reason is the way we save and restore the RCmodels with pytorch ANNs
# this enables the instantiation as cls(**call_kwargs)
# optimizers need to be instatiable the same way as pytorch optimizers,
# i.e. the state_dict needs to have a key called param_groups,
# the list corresponding to taht key will be passed as first arg to optimizer


class FFNet(nn.Module):
    """
    Simple feedforward network with 4 hidden layers.
    n_in - number of input coordinates
    n_out - number of log probabilities to output,
            i.e. 1 for 2-state and N for N-State,
            make sure to use the correct loss
    """
    def __init__(self, n_in, n_out=1, activation=F.elu, **kwargs):
        super().__init__()
        self.call_kwargs = {'n_in': n_in,
                            'n_out': n_out,
                            'activation': activation
                            }
        self.activation = activation
        self.lay0 = nn.Linear(n_in, n_in)
        self.lay1 = nn.Linear(n_in, n_in)
        self.lay2 = nn.Linear(n_in, n_in)
        self.lay3 = nn.Linear(n_in, n_in)
        self.out_lay = nn.Linear(n_in, n_out)

    def forward(self, x):
        x = self.activation(self.lay0(x))
        x = self.activation(self.lay1(x))
        x = self.activation(self.lay2(x))
        x = self.activation(self.lay3(x))
        x = self.out_lay(x)
        return x