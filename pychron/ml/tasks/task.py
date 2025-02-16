# ===============================================================================
# Copyright 2019 Jake Ross
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
from traits.api import List, Int, HasTraits, Str, Bool
from traitsui.api import View, UItem, Item, HGroup, VGroup

# ============= standard library imports ========================
# ============= local library imports  ==========================

from pyface.tasks.task_layout import TaskLayout, PaneItem


class MachineLearningTask(BaseManagerTask):
    id = "pychron.machinelearning.task"

    def activated(self):
        pass

    def prepare_destroy(self):
        pass

    def create_dock_panes(self):
        return []

    def create_central_pane(self):
        pass

    def _default_layout_default(self):
        return TaskLayout()


# ============= EOF =============================================
