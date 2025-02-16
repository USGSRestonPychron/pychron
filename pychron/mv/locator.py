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
import time

from traits.api import Float

# ============= standard library imports ========================

from numpy import (
    array,
    histogram,
    argmax,
    zeros,
    asarray,
    ones_like,
    nonzero,
    max,
    arange,
    argsort,
    invert,
    median,
    mean,
    zeros_like,
)
from operator import attrgetter
from skimage.morphology import watershed
from skimage.draw import polygon, circle, circle_perimeter, circle_perimeter_aa
from scipy import ndimage
from skimage.exposure import rescale_intensity
from skimage.filters import gaussian
from skimage import feature

# ============= local library imports  ==========================
from pychron.loggable import Loggable
from pychron.mv.segment.region import RegionSegmenter
from pychron.image.cv_wrapper import (
    grayspace,
    draw_contour_list,
    contour,
    colorspace,
    get_polygons,
    get_size,
    new_point,
    draw_rectangle,
    draw_lines,
    draw_polygons,
    crop,
)
from pychron.mv.target import Target
from pychron.core.geometry.geometry import approximate_polygon_center, calc_length


def _coords_inside_image(rr, cc, shape):
    mask = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
    return rr[mask], cc[mask]


def draw_circle(frame, center_x, center_y, radius, color, **kw):
    cy, cx = circle(int(center_y), int(center_x), int(radius), shape=frame.shape)
    frame[cy, cx] = color


def draw_circle_perimeter(frame, center_x, center_y, radius, color):
    cy, cx = circle_perimeter(int(center_y), int(center_x), int(radius))

    cy, cx = _coords_inside_image(cy, cx, frame.shape)
    frame[cy, cx] = color


class Locator(Loggable):
    pxpermm = Float
    use_histogram = False
    use_arc_approximation = True
    use_square_approximation = True
    step_signal = None
    pixel_depth = 255

    alive = True

    def cancel(self):
        self.debug("canceling")
        self.alive = False

    def wait(self):
        if self.step_signal:
            self.step_signal.wait()
            self.step_signal.clear()

    def crop(self, src, cw, ch, ox=0, oy=0, verbose=True):

        cw_px = int(cw * self.pxpermm)
        ch_px = int(ch * self.pxpermm)
        w, h = get_size(src)

        x = int((w - cw_px) / 2.0 + ox)
        y = int((h - ch_px) / 2.0 - oy)

        # r = 4 - cw_px % 4
        # cw_px = ch_px = cw_px + r
        if verbose:
            self.debug(
                "Crop: x={},y={}, cw={}, ch={}, "
                "width={}, height={}, ox={}, oy={}".format(
                    x, y, cw_px, ch_px, w, h, ox, oy
                )
            )
        return asarray(crop(src, x, y, cw_px, ch_px))

    def find(self, image, frame, dim, shape="circle", **kw):
        """
        image is a stand alone image
        dim = float. radius or half length of a square in pixels

        find the hole in the image

        return the offset from the center of the image

        0. image is alredy cropped
        1. find polygons

        """
        self.alive = True
        dx, dy = None, None

        targets = self._find_targets(image, frame, dim, shape=shape, **kw)

        if targets:
            self.info("found {} potential targets".format(len(targets)))

            # draw center indicator
            src = image.source_frame
            self._draw_center_indicator(src, size=2, shape="rect", radius=round(dim))

            # draw targets
            self._draw_targets(src, targets)

            if shape == "circle":
                if self.use_arc_approximation:
                    # calculate circle_minimization position
                    dx, dy = self._arc_approximation(src, targets[0], dim)
                else:
                    dx, dy = self._calculate_error(targets)
            else:
                dx, dy = self._calculate_error(targets)
                # if self.use_square_approximation:
                #     dx, dy = self._square_approximation(src, targets[0], dim)

                # image.set_frame(src[:])

        self.info("dx={}, dy={}".format(dx, dy))
        return dx, dy

    def _find_targets(
        self,
        image,
        frame,
        dim,
        shape="circle",
        search=None,
        preprocess=True,
        filter_targets=True,
        convexity_filter=False,
        mask=False,
        set_image=True,
        inverted=False,
    ):
        """
        use a segmentor to segment the image
        """

        if search is None:
            search = {}

        if preprocess:
            if not isinstance(preprocess, dict):
                preprocess = {}
            src = self._preprocess(frame, **preprocess)
        else:
            src = grayspace(frame)

        if src is None:
            self.debug("Locator: src is None")
            return

        if mask:
            self._mask(src, mask)

        if inverted:
            src = invert(src)

        blocksize_step = search.get("blocksize_step", 5)
        seg = RegionSegmenter(
            use_adaptive_threshold=search.get("use_adaptive_threshold", False),
            blocksize=search.get("blocksize", 20),
        )
        fa = self._get_filter_target_area(shape, dim)
        phigh, plow = None, None

        for low, high in self._generate_steps(src, search)():
            if not self.alive:
                self.debug("canceled")
                return

            self.debug("bandwidth low={}, high={}".format(low, high))

            if inverted:
                low = 255 - low
                high = 255 - high

            seg.threshold_low = low
            seg.threshold_high = high

            if seg.threshold_low == plow and seg.threshold_high == phigh:
                return

            plow = seg.threshold_low
            phigh = seg.threshold_high

            nsrc = seg.segment(src)
            seg.blocksize += blocksize_step

            nf = colorspace(nsrc)

            # draw contours
            targets = self._find_polygon_targets(nsrc, frame=nf)
            if set_image and image is not None:
                image.set_frame(nf)

            if targets:

                # filter targets
                if filter_targets:
                    targets = self._filter_targets(image, frame, dim, targets, fa)
                elif convexity_filter:
                    # for t in targets:
                    #     print t.convexity, t.area, t.min_enclose_area, t.perimeter_convexity
                    targets = [
                        t for t in targets if t.perimeter_convexity > convexity_filter
                    ]

            if targets:
                return sorted(targets, key=attrgetter("area"), reverse=True)
                # time.sleep(0.5)

    def _generate_steps(self, src, search):
        if search.get("use_adaptive_threshold"):

            def func():
                yield 0, 255

        elif search.get("use_new_style", True):

            def func():
                me = int(mean(src[src > 0]))
                bands = [2 ** n for n in range(7, 1, -1)]
                shifts = [2, 4, 8]

                for band in bands:
                    for shift in shifts:
                        for shift_dir in (1, -1):
                            for i in range(1, 128):
                                m = me - shift * i * shift_dir
                                low = m - band / 2
                                high = low + band
                                if low < 0 or high > 255:
                                    break

                                yield low, high

        else:

            def func():
                start = search.get("start")
                if start is None:
                    w = search.get("width", 10)
                    start = (
                        int(mean(src[src > 0]))
                        - search.get("start_offset_scalar", 3) * w
                    )

                step = search.get("step", 2)
                n = search.get("n", 20)

                for j in range(n):
                    ww = w * (j + 1)
                    for i in range(n):
                        low = max((0, start + i * step - ww))
                        high = max((1, min((255, start + i * step + ww))))
                        yield low, high

        return func

    def _mask(self, src, radius=None):

        radius *= self.pxpermm
        h, w = src.shape[:2]
        c = circle(h / 2.0, w / 2.0, radius, shape=(h, w))
        mask = ones_like(src, dtype=bool)
        mask[c] = False
        src[mask] = 0

        return invert(mask)

    # ===============================================================================
    # filter
    # ===============================================================================

    def _filter_targets(self, image, frame, dim, targets, fa, threshold=0.85):
        """
        filter targets using the _filter_test function

        return list of Targets that pass _filter_test
        """

        ts = [
            self._filter_test(image, frame, ti, dim, threshold, fa[0], fa[1])
            for ti in targets
        ]
        return [ta[0] for ta in ts if ta[1]]

    def _filter_test(self, image, frame, target, dim, cthreshold, mi, ma):
        """
        if the convexity of the target is <threshold try to do a watershed segmentation

        make black image with white polygon
        do watershed segmentation
        find polygon center

        """
        ctest, centtest, atest = self._test_target(frame, target, cthreshold, mi, ma)
        # print('ctest', ctest, cthreshold, 'centtest', centtest, 'atereat', atest, mi, ma)
        result = ctest and atest and centtest
        if not ctest and (atest and centtest):
            target = self._segment_polygon(
                image, frame, target, dim, cthreshold, mi, ma
            )
            result = True if target else False

        return target, result

    def _test_target(self, frame, ti, cthreshold, mi, ma):
        # print('converasdf', ti.convexity, 'ara', ti.area)
        ctest = ti.convexity > cthreshold
        centtest = self._near_center(ti.centroid, frame)
        atest = ma > ti.area > mi

        return ctest, centtest, atest

    def _find_polygon_targets(self, src, frame=None):
        src, contours, hieararchy = contour(src)
        # contours, hieararchy = find_contours(src)

        # convert to color for display
        if frame is not None:
            draw_contour_list(frame, contours, hieararchy)

        # do polygon approximation
        origin = self._get_frame_center(src)
        pargs = get_polygons(src, contours, hieararchy)
        return self._make_targets(pargs, origin)

    def _segment_polygon(self, image, frame, target, dim, cthreshold, mi, ma):

        src = frame[:]

        wh = get_size(src)
        # make image with polygon
        im = zeros(wh)
        points = asarray(target.poly_points)

        rr, cc = polygon(*points.T)
        im[cc, rr] = 255

        # do watershedding
        distance = ndimage.distance_transform_edt(im)
        local_maxi = feature.peak_local_max(distance, labels=im, indices=False)
        markers, ns = ndimage.label(local_maxi)
        wsrc = watershed(-distance, markers, mask=im)
        wsrc = wsrc.astype("uint8")

        #         self.test_image.setup_images(3, wh)
        #         self.test_image.set_image(distance, idx=0)
        #         self.test_image.set_image(wsrc, idx=1)

        #         self.wait()

        targets = self._find_polygon_targets(wsrc)
        ct = cthreshold * 0.75
        target = self._test_targets(wsrc, targets, ct, mi, ma)
        if not target:
            values, bins = histogram(wsrc, bins=max((10, ns)))
            # assume 0 is the most abundant pixel. ie the image is mostly background
            values, bins = values[1:], bins[1:]
            idxs = nonzero(values)[0]

            """
                polygon is now segmented into multiple regions
                consectutively remove a region and find targets
            """
            nimage = ones_like(wsrc, dtype="uint8") * 255
            nimage[wsrc == 0] = 0
            for idx in idxs:
                bl = bins[idx]
                bu = bins[idx + 1]
                nimage[((wsrc >= bl) & (wsrc <= bu))] = 0

                targets = self._find_polygon_targets(nimage)
                target = self._test_targets(nimage, targets, ct, mi, ma)
                if target:
                    break

        return target

    def _test_targets(self, src, targets, ct, mi, ma):
        if targets:
            for ti in targets:
                if all(self._test_target(src, ti, ct, mi, ma)):
                    return ti

    # ===============================================================================
    # preprocessing
    # ===============================================================================
    def _preprocess(self, frame, stretch_intensity=True, blur=1, denoise=0):
        """
        1. convert frame to grayscale
        2. remove noise from frame. increase denoise value for more noise filtering
        3. stretch contrast
        """
        if len(frame.shape) != 2:
            frm = grayspace(frame) * 255
        else:
            frm = frame / self.pixel_depth * 255

        frm = frm.astype("uint8")

        # self.preprocessed_frame = frame
        # if denoise:
        #     frm = self._denoise(frm, weight=denoise)
        # print 'gray', frm.shape
        if blur:
            frm = gaussian(frm, blur) * 255
            frm = frm.astype("uint8")

            # frm1 = gaussian(self.preprocessed_frame, blur,
            #                 multichannel=True) * 255
            # self.preprocessed_frame = frm1.astype('uint8')

        if stretch_intensity:
            frm = rescale_intensity(frm)
            # frm = self._contrast_equalization(frm)
            # self.preprocessed_frame = self._contrast_equalization(self.preprocessed_frame)

        return frm

    def _denoise(self, img, weight):
        """
        use TV-denoise to remove noise

        http://scipy-lectures.github.com/advanced/image_processing/
        http://en.wikipedia.org/wiki/Total_variation_denoising
        """

        from skimage.filters import denoise_tv_chambolle

        img = denoise_tv_chambolle(img, weight=weight) * 255

        return img.astype("uint8")

    # def _contrast_equalization(self, img):
    #     """
    #         rescale intensities to maximize contrast
    #     """
    #     #        from numpy import percentile
    #     # Contrast stretching
    #     #        p2 = percentile(img, 2)
    #     #        p98 = percentile(img, 98)
    #
    #     return rescale_intensity(asarray(img))

    # ===============================================================================
    # deviation calc
    # ===============================================================================
    # def _square_approximation(self, src, target, dim):
    # tx, ty = self._get_frame_center(src)
    # pts = target.poly_points
    #
    #
    # cx, cy = dx + tx, dy + ty
    # dy = -dy
    # self._draw_indicator(src, (cx, cy), color=(255, 0, 128), shape='crosshairs')
    #
    # return dx, dy

    def _arc_approximation(self, src, target, dim):
        """
        find cx,cy of a circle with r radius using the arc center method

        only preform if target has high convexity
        convexity is simply defined as ratio of area to convex hull area

        """
        tol = 0.8
        if target.convexity > tol:
            self.info("doing arc approximation radius={}".format(dim))
            tx, ty = self._get_frame_center(src)
            pts = target.poly_points
            pts[:, 1] = pts[:, 1] - ty
            pts[:, 0] = pts[:, 0] - tx
            dx, dy = approximate_polygon_center(pts, dim)
            cx, cy = dx + tx, dy + ty
            dy = -dy

            self._draw_indicator(src, (cx, cy), color=(255, 0, 128), shape="crosshairs")
            draw_circle_perimeter(src, cx, cy, round(dim), color=(255, 0, 128))

        else:
            dx, dy = self._calculate_error([target])

        return dx, dy

    def _calculate_error(self, targets):
        """
        calculate the dx,dy
        deviation of the targets centroid from the center of the image
        """

        def hist(d):
            f, v = histogram(array(d))
            i = len(f) if argmax(f) == len(f) - 1 else argmax(f)
            return v[i]

        devxs, devys = list(zip(*[r.dev_centroid for r in targets]))

        if len(targets) > 2 and self.use_histogram:
            dx = hist(devxs)
            dy = hist(devys)
        else:

            def avg(s):
                return sum(s) / len(s)

            dx = avg(devxs)
            dy = avg(devys)

        return -dx, dy

    # ===============================================================================
    # helpers
    # ===============================================================================
    def _make_targets(self, pargs, origin):
        """
        convenience function for assembling target list
        """
        targets = []
        for pi, ai, co, ci, pa, pch, mask in pargs:
            if len(pi) < 5:
                continue

            tr = Target()
            tr.origin = origin
            tr.poly_points = pi
            #            tr.bounding_rect = br
            tr.area = ai
            tr.min_enclose_area = co
            tr.centroid = ci
            tr.pactual = pa
            tr.pconvex_hull = pch
            tr.mask = mask
            targets.append(tr)

        return targets

    def _filter(self, targets, func, *args, **kw):
        return [ti for ti in targets if func(ti, *args, **kw)]

    def _target_near_center(self, target, *args, **kw):
        return self._near_center(target.centroid, *args, **kw)

    def _near_center(self, xy, frame, tol=0.75):
        """
        is the point xy within tol distance of the center
        """
        cxy = self._get_frame_center(frame)
        d = calc_length(xy, cxy)
        tol *= self.pxpermm
        return d < tol

    def _get_filter_target_area(self, shape, dim):
        """
        calculate min and max bounds of valid polygon areas
        """
        if shape == "circle":
            miholedim = 0.5 * dim
            maholedim = 1.25 * dim
            mi = miholedim ** 2 * 3.1415
            ma = maholedim ** 2 * 3.1415
        else:
            d = (2 * dim) ** 2
            mi = 0.5 * d
            ma = 1.25 * d

        return mi, ma

    def _get_frame_center(self, src):
        """
        convenience function for geting center of image in c,r from
        """
        w, h = get_size(src)
        x = w / 2
        y = h / 2

        return x, y

    # ===============================================================================
    # draw
    # ===============================================================================
    def _draw_targets(self, src, targets):
        """
        draw a crosshairs indicator
        """
        if targets:
            for ta in targets:
                pt = new_point(*ta.centroid)
                self._draw_indicator(
                    src, pt, color=(0, 255, 0), size=10, shape="crosshairs"
                )
                # draw_circle(src, pt,
                #             color=(0,255,0),
                #             radius=int(dim))

                draw_polygons(src, [ta.poly_points], color=(255, 255, 255))

    def _draw_center_indicator(
        self, src, color=(0, 0, 255), shape="crosshairs", size=10, radius=1
    ):
        """
        draw indicator at center of frame
        """
        cpt = self._get_frame_center(src)
        self._draw_indicator(
            src,
            new_point(*cpt),
            #                             shape='crosshairs',
            shape=shape,
            color=color,
            size=size,
        )

        # draw_circle_perimeter(src, cpt[0], cpt[1], radius, color=color)

    def _draw_indicator(
        self, src, center, color=(255, 0, 0), shape="circle", size=4, thickness=-1
    ):
        """
        convenience function for drawing indicators
        """
        if isinstance(center, tuple):
            center = new_point(*center)
        r = size
        if shape == "rect":
            draw_rectangle(
                src,
                center.x - r / 2.0,
                center.y - r / 2.0,
                r,
                r,
                color=color,
                thickness=thickness,
            )
        elif shape == "crosshairs":
            draw_lines(
                src,
                [
                    [(center.x - size, center.y), (center.x + size, center.y)],
                    [(center.x, center.y - size), (center.x, center.y + size)],
                ],
                color=color,
                thickness=1,
            )
        else:
            draw_circle(src, center[0], center[1], r, color=color)


# ============= EOF =============================================
#  def _segment_polygon2(self, image, frame, target,
#                          dim,
#                          cthreshold, mi, ma):
#
#         pychron = image.source_frame[:]
#
# #         find the label with the max area ie max of histogram
#         def get_limits(values, bins, width=1):
#             ind = argmax(values)
#             if ind == 0:
#                 bil = bins[ind]
#                 biu = bins[ind + width]
#             elif ind == len(bins) - width:
#                 bil = bins[ind - width]
#                 biu = bins[ind]
#             else:
#                 bil = bins[ind - width]
#                 biu = bins[ind + width]
#
#             return bil, biu, ind
#
#         wh = get_size(pychron)
#         # make image with polygon
#         im = zeros(wh)
#         points = asarray(target.poly_points)
#         rr, cc = polygon(*points.T)
#
#         #            points = asarray([(pi.x, pi.y) for pi in points])
#         #            rr, cc = polygon(points[:, 0], points[:, 1])
#
#         im[cc, rr] = 255
#
#         # do watershedding
#         distance = ndimage.distance_transform_edt(im)
#         local_maxi = feature.peak_local_max(distance, labels=im,
#                                             indices=False,
#                                             footprint=ones((3, 3))
#                                             )
#         markers, ns = ndimage.label(local_maxi)
# #
#         wsrc = watershed(-distance, markers,
#                         mask=im
#                         )
#
# #         print wsrc[50]
# #         print colorspace(distance)
# #         debug_show(im, ws, seg1)
# #         debug_show(im, distance, wsrc, nimage)
#         # bins = 3 * number of labels. this allows you to precisely pick the value of the max area
#         values, bins = histogram(wsrc, bins=ns * 3)
#         bil, biu, ind = get_limits(values, bins)
# #         ma = max()
# #         print ma
# #         nimage = ndimage.label(wsrc > biu)[0]
#
# #         nimage = nimage.astype('uint8') * 255
#         if not bil:
#             values = delete(values, ind)
#             bins = delete(bins, (ind, ind + 1))
#             bil, biu, ind = get_limits(values, bins)
# #
#         nimage = ones_like(wsrc, dtype='uint8') * 255
#         nimage[wsrc < bil] = 0
#         nimage[wsrc > biu] = 0
#
# #         image.source_frame = colorspace(nimage)
#
# #         image.refresh = True
# #         time.sleep(1)
#
# #         debug_show(im, distance, wsrc, nimage)
#         nimage = invert(nimage)
# #         img = nimage
# #         #            img = asMat(nimage)
# #         # locate new polygon from the segmented image
#         tars = self._find_targets(image, nimage, dim,
#                                   start=10, w=4, n=2, set_image=False)
# #         #            tars = None
# #         #                do_later(lambda: self.debug_show(im, distance, wsrc, nimage))
#
# #         tars = None
#         if tars:
#             target = tars[0]
#             return self._test_target(frame, target, cthreshold, mi, ma)
#         else:
#             return False, False, False

#        from numpy import linspace, pi, cos, sin, radians
#        from math import atan2
#        from scipy.optimize import fmin
# #        dx, dy = None, None
# #        for ta in targets:
#        pts = array([(p.x, p.y) for p in target.poly_points], dtype=float)
#        pts = sort_clockwise(pts, pts)
#        pts = convex_hull(pts)
#        cx, cy = target.centroid
#        px, py = pts.T
#
#        tx, ty = self._get_frame_center(pychron)
#        px -= cx
#        py -= cy
#
#        r = dim * 0.5
#        ts = array([atan2(p[1] - cx, p[0] - cy) for p in pts])
# #        ts += 180
#        n = len(ts)
#        hidx = n / 2
#        h1 = ts[:hidx]
#
#        offset = 0 if n % 2 == 0 else 1
#
# #        h1 = array([ti for ti in ts if ti < 180])
# #        h1 = radians(h1)
# #        hidx = len(h1)
# #        print len(ts), hidx
# #        offset = 0
#        def cost(p0):
#            '''
#                cost function
#
#                A-D: chord of the polygon
#                B-C: radius of fit circle
#
#                A  B             C  D
#
#                try to minimize difference fit circle and polygon approx
#                cost=dist(A,B)+dist(C,D)
#            '''
# #            r = p0[2]
#            # northern hemicircle
#            cix1, ciy1 = p0[0] - cx + r * cos(h1), p0[1] - cy + r * sin(h1)
#
#            # southern hemicircle
#            cix2, ciy2 = p0[0] - cx + r * cos(h1 + pi), p0[1] - cy + r * sin(h1 + pi)
#
#            dx, dy = px[:hidx] - cix1, py[:hidx] - ciy1
#            p1 = (dx ** 2 + dy ** 2) ** 0.5
#
# #            dx, dy = cix2 - px[hidx + offset:], ciy2 - py[hidx + offset:]
#            dx, dy = px[hidx + offset:] - cix2, py[hidx + offset:] - ciy2
#            p2 = (dx ** 2 + dy ** 2) ** 0.5
# #            print 'p1', p1
# #            print 'p2', p2
#            return ((p2 - p1) ** 2).sum()
# #            return (p1 + p2).mean()
# #            return p2.sum() + p1.sum()
#
#        # minimize the cost function
#        dx, dy = fmin(cost, x0=[0, 0], disp=False)  # - ta.centroid
#        print dx, dy, ty, cy
# #        dy -= cy
# #        dx -= cx
#
# #        print ty + cy, dy
#        self._draw_indicator(pychron, (dx, dy), shape='rect')
#        draw_circle(pychron, (dx, dy), int(r))
#
#        return dx - target.origin[0], dy - target.origin[1]
# def debug_show(image, distance, wsrc, nimage):
#
#    import matplotlib.pyplot as plt
#    fig, axes = plt.subplots(ncols=4, figsize=(8, 2.7))
#    ax0, ax1, ax2, ax3 = axes
#
#    ax0.imshow(image, cmap=plt.cm.gray, interpolation='nearest')
#    ax1.imshow(-distance, cmap=plt.cm.jet, interpolation='nearest')
#    ax2.imshow(wsrc, cmap=plt.cm.jet, interpolation='nearest')
#    ax3.imshow(nimage, cmap=plt.cm.jet, interpolation='nearest')
#
#    for ax in axes:
#        ax.axis('off')
#
#    plt.subplots_adjust(hspace=0.01, wspace=0.01, top=1, bottom=0, left=0,
#                    right=1)
#    plt.show()
#     def find_circle(self, image, frame, dim, **kw):
#         dx, dy = None, None
#
#         pframe = self._preprocess(frame, blur=0)
#         edges = canny(pframe, sigma=3)
#         hough_radii = arange(dim * 0.9, dim * 1.1, 2)
#
#         hough_res = hough_circle(edges, hough_radii)
#
#         centers = []
#         accums = []
#         radii = []
#         for radius, h in zip(hough_radii, hough_res):
#             # For each radius, extract two circles
#             num_peaks = 2
#             peaks = peak_local_max(h, num_peaks=num_peaks)
#             centers.extend(peaks)
#             accums.extend(h[peaks[:, 0], peaks[:, 1]])
#             radii.extend([radius] * num_peaks)
#
#         # for idx in argsort(accums)[::-1][:1]:
#         try:
#             idx = argsort(accums)[::-1][0]
#         except IndexError:
#             return dx, dy
#
#         center_y, center_x = centers[idx]
#         radius = radii[idx]
#
#         draw_circle_perimeter(frame, center_x, center_y, radius, (220, 20, 20))
#         # cx, cy = circle_perimeter(int(center_x), int(center_y), int(radius))
#
#         # draw perimeter
#         # try:
#         #     frame[cy, cx] = (220, 20, 20)
#         # except IndexError:
#         #     pass
#
#         # draw center
#         # cx, cy = circle(int(center_x), int(center_y), int(2))
#         # frame[cy, cx] = (220, 20, 20)
#         draw_circle(frame, center_x, center_y, 2, (220, 20, 20))
#
#         h, w = frame.shape[:2]
#
#         ox, oy = w / 2, h / 2
#         dx = center_x - ox
#         dy = center_y - oy
#
#         cx, cy = circle(int(ox), int(oy), int(2))
#         frame[cy, cx] = (20, 220, 20)
#
#         image.set_frame(frame)
#         return float(dx), -float(dy)
