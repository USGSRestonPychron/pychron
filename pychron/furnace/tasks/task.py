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
from pyface.tasks.task_layout import TaskLayout, PaneItem
# ============= standard library imports ========================
# ============= local library imports  ==========================
from pychron.envisage.tasks.base_task import BaseManagerTask
from pychron.furnace.tasks.panes import FurnacePane, LDEOFurnacePane, ControlPane, LDEOControlPane


class FurnaceTask(BaseManagerTask):
    id = 'pychron.furnace.task'
    name = 'Furnace'

    def activated(self):
        self.manager.activate()

    def prepare_destroy(self):
        self.manager.prepare_destroy()

    def create_dock_panes(self):
        return [ControlPane(model=self.manager)]

    def create_central_pane(self):
        return FurnacePane(model=self.manager)

    def _default_layout_default(self):
        return TaskLayout(left=PaneItem('pychron.nmgrlfurnace.controls'))

class LDEOFurnaceTask(BaseManagerTask):
    id = 'pychron.ldeo.furnace.task'
    name = 'LDEO Furnace'

    def activated(self):
        self.manager.activate()

    def prepare_destroy(self):
        self.manager.prepare_destroy()

    def create_dock_panes(self):
        return [LDEOControlPane(model=self.manager)]

    def create_central_pane(self):
        return LDEOFurnacePane(model=self.manager)

    def _default_layout_default(self):
        return TaskLayout(left=PaneItem('pychron.ldeofurnace.controls'))

# ============= EOF =============================================
