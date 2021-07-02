# ===============================================================================
# Copyright 2012 Jake Ross
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
from __future__ import absolute_import

from apptools.preferences.preference_binding import bind_preference
from traits.api import Float, Button, Bool, Any, Instance, Event, Int
from traitsui.api import View, Item, HGroup, RangeEditor
from math import ceil
from pychron.image.standalone_image import FrameImage
from pychron.mv.machine_vision_manager import MachineVisionManager, view_image


class AutoCenterManager(MachineVisionManager):
    canvas = Any

    # use_crop_size = Bool(False)
    # use_target_radius = Bool(False)

    # crop_size = Float(4)
    # target_radius = Float(1.0)

    configure_button = Button('configure')
    use_autocenter = Bool
    # use_hough_circle = Bool(False)

    use_adaptive_threshold = Bool(False)
    blur = Int
    stretch_intensity = Bool(False)
    search_step = Int
    search_n = Int
    search_width = Int
    blocksize = Int
    blocksize_step = Int

    display_image = Instance(FrameImage, ())

    locator = None

    def bind_preferences(self, pref_id):
        bind_preference(self, 'use_autocenter', '{}.use_autocenter'.format(pref_id))
        bind_preference(self, 'blur', '{}.autocenter_blur'.format(pref_id))
        bind_preference(self, 'stretch_intensity', '{}.autocenter_stretch_intensity'.format(pref_id))
        bind_preference(self, 'use_adaptive_threshold', '{}.autocenter_use_adaptive_threshold'.format(pref_id))
        bind_preference(self, 'search_step', '{}.autocenter_search_step'.format(pref_id))
        bind_preference(self, 'search_n', '{}.autocenter_search_n'.format(pref_id))
        bind_preference(self, 'search_width', '{}.autocenter_search_width'.format(pref_id))
        bind_preference(self, 'blocksize', '{}.autocenter_blocksize'.format(pref_id))
        bind_preference(self, 'blocksize_step', '{}.autocenter_blocksize_step'.format(pref_id))

    def cancel(self):
        self.debug('canceling')
        if self.locator:
            self.locator.cancel()

    # def clear_cache(self):
    #     self.debug('clear locator cache')
    #     if self.locator:
    #         self.locator.clear_cache()

    def calculate_new_center(self, cx, cy, offx, offy, dim=1.0, shape='circle'):
        frame = self.new_image_frame()
        loc = self._get_locator(shape=shape)
        self.locator = loc

        self.debug('dim={} pxpermm={}, loc.pxpermm={}'.format(dim, self.pxpermm, loc.pxpermm))
        cropdim = ceil(dim * 2.55)

        # frame = loc.rescale(frame, 1.5)
        frame = loc.crop(frame, cropdim, cropdim, offx, offy)

        dim = self.pxpermm * dim

        im = self.display_image
        im.source_frame = frame

        preprop = {'stretch_intensity': self.stretch_intensity,
                   'blur': self.blur}
        search = dict(n=self.search_n,
                      step=self.search_step,
                      width=self.search_width,
                      blocksize=self.blocksize,
                      blocksize_step=self.blocksize_step,
                      use_adaptive_threshold=self.use_adaptive_threshold)

        dx, dy = loc.find(im, frame, dim=dim, preprocess=preprop, search=search, use_threshold_caching=True)

        if dx is None and dy is None:
            return
        else:
            # pdx, pdy = round(dx), round(dy)
            mdx = dx / self.pxpermm
            mdy = dy / self.pxpermm
            self.info('calculated deviation px={:n},{:n}, '
                      'mm={:0.3f},{:0.3f} ({})'.format(dx, dy, mdx, mdy, self.pxpermm))
            return cx + mdx, cy + mdy

    # private
    def _get_locator(self, *args, **kw):
        raise NotImplementedError

    # handlers
    def _configure_button_fired(self):
        w = h = self.crop_size * self.pxpermm
        canvas = self.canvas
        if canvas:
            cx, cy = canvas.get_center_rect_position(w, h)

            canvas.add_markup_rect(cx, cy, w, h, identifier='croprect')

            cx, cy = canvas.get_screen_center()
            r = self.target_radius * self.pxpermm
            canvas.add_markup_circle(cx, cy, r, identifier='target')

        self.edit_traits(view='configure_view', kind='livemodal')
        if canvas:
            canvas.remove_item('croprect')
            canvas.remove_item('target')

    def _crop_size_changed(self):
        canvas = self.canvas
        if canvas:
            canvas.remove_item('croprect')

            w = h = self.crop_size * self.pxpermm
            cx, cy = canvas.get_center_rect_position(w, h)

            canvas.add_markup_rect(cx, cy, w, h, identifier='croprect')

    def _target_radius_changed(self):
        canvas = self.canvas
        if canvas:
            canvas.remove_item('target')
            r = self.target_radius * self.pxpermm
            cx, cy = canvas.get_screen_center()
            canvas.add_markup_circle(cx, cy, r, identifier='target')

            # views
            # def configure_view(self):
            #     v = View(Item('crop_size'),
            #              Item('target_radius', editor=RangeEditor(low=0., high=5.)),
            #              buttons=['OK', 'Cancel'])
            #     return v
            #
            # def traits_view(self):
            #     v = View(HGroup(Item('use_autocenter', label='Enabled'),
            #                     # Item('configure_button', show_label=False),
            #                     show_border=True,
            #                     label='Autocenter'))
            #     return v


class CO2AutocenterManager(AutoCenterManager):
    # private
    def _get_locator(self, *args, **kw):
        if self.locator:
            loc = self.locator
        else:
            from pychron.mv.co2_locator import CO2Locator
            loc = CO2Locator(pxpermm=self.pxpermm, pixel_depth=self.video.pixel_depth)
        loc.pxpermm = self.pxpermm
        loc.pixel_depth = self.video.pixel_depth
        return loc


class DiodeAutocenterManager(AutoCenterManager):
    # private
    def _get_locator(self, *args, **kw):
        from pychron.mv.diode_locator import DiodeLocator
        return DiodeLocator(pxpermm=self.pxpermm, pixel_depth=self.video.pixel_depth)

# ============= EOF =============================================
