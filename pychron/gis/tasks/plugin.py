# ===============================================================================
# Copyright 2018 ross
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
from traits.api import List

from pychron.envisage.tasks.base_task_plugin import BaseTaskPlugin
from pychron.gis.nodes import GISNode
from pychron.gis.tasks.predefined import GIS


class GISPlugin(BaseTaskPlugin):
    nodes = List(contributes_to='pychron.pipeline.nodes')
    predefined_templates = List(contributes_to='pychron.pipeline.predefined_templates')
    pipeline_group_icon_map = List(contributes_to='pychron.pipeline.pipeline_group_icon_map')

    # def _preferences_panes_default(self):
    #     return [MDDPreferencesPane]

    def _pipeline_group_icon_map_default(self):
        return [('GIS', 'world')]

    def _predefined_templates_default(self):
        return [('GIS', (('Map', GIS),
                         ))]

    def _nodes_default(self):
        return [GISNode]

# ============= EOF =============================================
