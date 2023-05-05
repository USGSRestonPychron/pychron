# ===============================================================================
# Copyright 2023 Jake Ross
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
from pychron.hardware.gauges.base_controller import BaseGaugeController

PORT_MAPPING = {
    "IGC1": 1,
    "IGC2": 2,
    "PG1": 3,
    "PG2": 4,
    "CM1": 5,
    "CM2": 6,
    "CM3": 7,
    "CM4": 8,
    "AN1": 9,
    "AN2": 10,
    "AN3": 11,
    "AN4": 12,
}


class IGC100GaugeController(BaseGaugeController):
    def _read_pressure(self, gauge, *args, **kw):
        name = gauge.name
        port = PORT_MAPPING.get(name)
        if port is None:
            return self.ask(f"GDAT? {port}")

        self.warning(
            f"Invalid gauge name {name}. Valid names are {PORT_MAPPING.keys()}"
        )


# ============= EOF =============================================
