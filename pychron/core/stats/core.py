# ===============================================================================
# Copyright 2012 Jake Ross
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

# ============= standard library imports ========================

from numpy import asarray, average, vectorize

# ============= local library imports  ==========================
from scipy.stats import chi2


def _kronecker(ii, jj):
    return int(ii == jj)


kronecker = vectorize(_kronecker)


def calculate_mswd(x, errs, k=1, wm=None):
    mswd_w = 0
    n = len(x)
    if n > k:
        x = asarray(x)
        errs = asarray(errs)
        if wm is None:
            wm, _err = calculate_weighted_mean(x, errs)

        ssw = (x - wm) ** 2 / errs ** 2
        mswd_w = ssw.sum() / float(n - k)

    return mswd_w


def calculate_weighted_mean(x, errs):
    x = asarray(x)
    errs = asarray(errs)

    idx = errs.astype(bool)

    errs = errs[idx]
    x = x[idx]

    weights = 1 / errs ** 2
    try:
        wmean, sum_weights = average(x, weights=weights, returned=True)
        werr = sum_weights ** -0.5
    except ZeroDivisionError:
        wmean = average(x)
        werr = 0

    return wmean, werr


def validate_mswd(mswd, n, k=1):
    """
    is mswd acceptable based on Mahon 1996

    does the mswd fall in the %95 confidence interval of the reduced chi2
    reduced chi2 =chi2/dof

    http://en.wikipedia.org/wiki/Goodness_of_fit
    http://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chi2.html#scipy.stats.chi2
    """
    # if n - k + 1 < 2:
    if n <= k:
        return False

    low, high = get_mswd_limits(n, k)
    return bool(low <= mswd <= high)


MSWD_LIMITS = {}


def get_mswd_limits(n, k=1):
    dof = n - k
    limits = MSWD_LIMITS.get(dof, None)
    if not limits:
        # calculate the reduced chi2 95% interval for given dof
        # use scale parameter to calculate the chi2_reduced from chi2
        rv = chi2(dof, scale=1 / float(dof))
        limits = rv.interval(0.95)
        MSWD_LIMITS[dof] = limits

    return limits


def chi_squared(x, y, sx, sy, a, b, corrcoeffs=None):
    """
    Press et. al 2007 Numerical Recipes
    chi2=Sum((y_i-(a+b*x_i)^2*W_i)
    where W_i=1/(sy_i^2+(b*sx_i)^2)

    a: y intercept
    b: slope

    Mahon 1996 modifies weights for correlated errors

    W_i=1/(sy_i^2+(b*sx_i)^2-k)

    k=2*b*p_i.*sx_i**2

    p: correlation_coefficient

    """
    x = asarray(x)
    y = asarray(y)

    sx = asarray(sx)
    sy = asarray(sy)

    k = 0
    if corrcoeffs is not None:
        # p=((1+(sy/y)**2)*(1+(sx/x)**2))**-2
        k = 2 * b * corrcoeffs * sx * sy

    w = (sy ** 2 + (b * sx) ** 2 - k) ** -1

    c = ((y - (a + b * x)) ** 2 * w).sum()

    return c


def calculate_mswd2(x, y, ex, ey, a, b, corrcoeffs=None):
    """
    see Murray 1994, Press 2007

    calculate chi2
    mswd=chi2/(n-2)
    """
    n = len(x)

    return chi_squared(x, y, ex, ey, a, b, corrcoeffs) / (n - 2)


def calculate_mswd_probability(mswd, dof):
    """
    replicates MassSpec's  StatsModule.ProbMSWD

    :param mswd:
    :param dof:
    :return:
    """
    return chi2.sf(mswd * dof, dof)


# ============= EOF =============================================
