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
import time

from pyface.timer.do_later import do_after
from traits.api import Instance
from traitsui.api import Item, VGroup

from pychron.canvas.canvas2D.furnace_canvas import FurnaceCanvas
from pychron.core.helpers.traitsui_shortcuts import okcancel_view
from pychron.furnace.base_stage_manager import BaseFurnaceStageManager
from pychron.hardware.linear_axis import LinearAxis


class Feeder(LinearAxis):
    pass


class ThermoFurnaceStageManager(BaseFurnaceStageManager):
    feeder = Instance(Feeder)

    slew_period = 1

    def feeder_slew(self, scalar):
        do_after(self.slew_period * 1000, self._slew_inprogress)
        self.feeder.slew(scalar)

    def feeder_stop(self):
        self.feeder.stop()

    def _slew_inprogress(self):
        self._update_axes()
        if self.feeder.is_slewing() and not self.feeder.is_stalled():
            do_after(self.slew_period * 1000, self._slew_inprogress)

    def refresh(self, warn=False):
        self._update_axes(warn=warn)

    def set_sample_dumped(self):
        hole = self.stage_map.get_hole(self.calibrated_position_entry)
        if hole:
            hole.analyzed = True
            self.canvas.request_redraw()

    def get_current_position(self):
        if self.feeder:
            x = self.feeder.position
            return x, 0

    def goto_position(self, v):
        self.move_to_hole(v)

    def in_motion(self):
        return self.feeder.moving()

    def relative_move(self, ax_key, direction, distance):
        self.feeder.slew(direction * distance)

    def key_released(self):
        self.feeder.stop()

    # private
    def _move_to_hole(self, key, correct_position=True):
        self.info("Move to hole {} type={}".format(key, str(type(key))))
        pos = self.stage_map.get_hole_pos(key)

        if pos:
            do_hystersis = self.temp_position and self.temp_position > pos

            self.temp_hole = key
            self.temp_position = pos

            x, y = self.get_calibrated_position(pos, key=key)
            self.info(
                "hole={}, position={}, calibrated_position={}".format(key, pos, (x, y))
            )
            if do_hystersis:
                self.info("doing hystersis")
                hx = x - 5
                self.debug("hystersis position={}".format(hx))
                self.canvas.set_desired_position(hx, 0)
                self.feeder._position = hx
                self.feeder.move_absolute(hx, units="mm")

                self._inprogress()

                self.info("Hystersis correction complete")
                self.update_axes()

            self.canvas.set_desired_position(x, 0)
            self.feeder._position = x
            self.feeder.move_absolute(x, units="mm")

            self._inprogress()

            self.info("Move complete")
            self.update_axes()  # update_hole=False)
        else:
            self.debug("invalid hole {}".format(key))

    def _inprogress(self, timeout=120):
        time.sleep(1)
        st = time.time()
        moving = self.feeder.moving
        update = self._update_axes

        cnt = 0
        while 1:
            if time.time() - st > timeout:
                break

            update()
            if not moving():
                cnt += 1
                if cnt > 2:
                    break
            else:
                cnt = 0
            time.sleep(0.5)

    def _update_axes(self, warn=False):
        pos = self.feeder.get_position(units="mm")
        self.debug("update feeder position={}".format(pos))
        if pos is None:
            if warn:
                self.warning_dialog(
                    "Could not read Feeder position. "
                    "Check that the furnace firmware computer is running and accessible"
                )
        elif pos == "No Response":
            if warn:
                self.warning_dialog(
                    "Could not read Feeder position. Check that the Feeder motor is plugged in"
                )
        elif pos is not None:
            self.canvas.set_stage_position(pos, 0)

    def _canvas_factory(self):
        c = FurnaceCanvas(feeder=self.feeder)
        return c

    def _feeder_default(self):
        d = Feeder(name="feeder", configuration_dir_name="furnace")
        return d


# ============= EOF =============================================
