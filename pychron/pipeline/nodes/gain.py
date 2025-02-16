# ===============================================================================
# Copyright 2015 Jake Ross
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ===============================================================================

# ============= enthought library imports =======================
from __future__ import absolute_import
from traits.api import HasTraits

# ============= standard library imports ========================
# ============= local library imports  ==========================
from pychron.pipeline.editors.gain_calibration_editor import GainCalibrationEditor
from pychron.pipeline.nodes.base import BaseNode
from pychron.pipeline.nodes.data import BaseDVCNode


class GainCalibrationOption(HasTraits):
    pass


class GainCalibrationNode(BaseDVCNode):
    options_klass = GainCalibrationOption
    name = "Gain Calibration"

    # def configure(self):
    #     ms = ['jan', 'obama']
    #     self.options.set_mass_spectrometers(ms)
    #
    #     self._configure(obj=self.options)

    def run(self, state):
        editor = GainCalibrationEditor(dvc=self.dvc)
        editor.initialize()
        state.editors.append(editor)


# ============= EOF =============================================
