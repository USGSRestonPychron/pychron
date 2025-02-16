# ===============================================================================
# Copyright 2013 Jake Ross
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ===============================================================================

# ============= enthought library imports =======================
# from traits.api import HasTraits
# from traitsui.api import View, Item
from __future__ import absolute_import
from pyface.tasks.task_window_layout import TaskWindowLayout

from pychron.applications.pychron_application import PychronApplication


# ============= standard library imports ========================
# ============= local library imports  ==========================


class PyCO2(PychronApplication):
    id = "pychron.co2.application"
    name = "pyCO2"
    shortname = "co2"

    default_layout = [
        TaskWindowLayout("tasks.hardware"),
        TaskWindowLayout("pychron.fusions.co2"),
    ]


# ============= EOF =============================================
