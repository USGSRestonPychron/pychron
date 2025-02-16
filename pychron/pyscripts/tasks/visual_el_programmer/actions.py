# ===============================================================================
# Copyright 2014 Jake Ross
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

from traitsui.menu import Action

# ============= standard library imports ========================
# ============= local library imports  ==========================
from pychron.envisage.tasks.actions import FileOpenAction, NewAction


class SwitchRenamerAction(Action):
    name = "Switch Renamer..."

    def perform(self, event):
        from pychron.pyscripts.switch_renamer import SwitchRenamer

        sr = SwitchRenamer()
        sr.edit_traits()


class OpenVisualELScriptAction(FileOpenAction):
    name = "Open Visual PyScript..."
    task_id = "pychron.pyscript.visual_el_programmer"


class NewVisualELScriptAction(NewAction):
    task_id = "pychron.pyscript.visual_el_programmer"
    name = "New Visual PyScript"


# ============= EOF =============================================
