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

def main(ctx):
  return [
    make_pip_pipeline(os="linux", arch="amd64", py_version="3.5"),
    make_pip_pipeline(os="linux", arch="amd64", py_version="3.6"),
    make_pip_pipeline(os="linux", arch="amd64", py_version="3.7"),
    make_pip_pipeline(os="linux", arch="amd64", py_version="3.8"),
    make_conda_pipeline(os="linux", arch="amd64", py_version="3.5"),
    make_conda_pipeline(os="linux", arch="amd64", py_version="3.6"),
    make_conda_pipeline(os="linux", arch="amd64", py_version="3.7"),
    # no tensorflow conda package for py3.8 yet
    #make_conda_pipeline(os="linux", arch="amd64", py_version="3.8"),
  ]

def make_pip_pipeline(os, arch, py_version):
  return {
    "kind": "pipeline",
    "name": "{0}-{1}-py{2}".format(os, arch, py_version),
    "platform": {
      "os": os,
      "arch": arch,
    },
    "steps": [
      {
        "name": "test",
        "image": "python:{0}".format(py_version),
        "commands": [
          "pip install --upgrade pip",
          "python --version",
          "pip --version",
          "pip list",
          # install ops pathsampling hooks branch
          "pip install git+https://github.com/hejung/openpathsampling.git@PathSampling_Hooks",
          # TODO: this is hardcoded and not nice for maintenance
          # install deep learning packages
          "pip install torch==1.4.0+cpu -f https://download.pytorch.org/whl/torch_stable.html",
          "pip install tensorflow",
          "pip install numpy cython",  # install setup dependecies
          "pip install .[test]",
          "pip list",
          "pytest -v -rs .",
        ]
      },
    ]
  }

# NOTE: we use our own docker repo where we have a conda container
#         where /bin/sh is a symlink to /bin/bash, this gets conda to work
# NOTE 2: Do **not** use conda activate, it does not propagate the exit code
#       ...so we could have sliently failing tests!
def make_conda_pipeline(os, arch, py_version):
  return {
    "kind": "pipeline",
    "name": "{0}-{1}-conda-py{2}".format(os, arch, py_version),
    "platform": {
      "os": os,
      "arch": arch,
    },
    "steps": [
      {
        "name": "test",
        "image": "hejung/conda3-drone",
        "commands": [
          # NOTE: need to use conda run, because conda activate does not work
          "conda config --prepend channels conda-forge",
          "conda config --append channels omnia",
          "conda update -n base conda -q -y",
          "conda --version",
          "conda create -n test_env -q -y python={0} compliers".format(py_version),
          "source activate test_env",
          "conda info -e",
          "python --version",
          "conda install tensorflow -y -q",
          # TODO: this is CPUonly hardcoded...
          "conda install -q torchvision cpuonly -c pytorch -y",
          "conda install -q numpy cython -y",  # install setup dependecies
          # install ops pathsampling hooks branch
          "pip install git+https://github.com/hejung/openpathsampling.git@PathSampling_Hooks",
          # install deep learning packages
          "conda list",
          "pip install .[test]",
          "pytest -v -rs .",
        ]
      },
    ]
  }
