from __future__ import division, print_function, absolute_import

import numpy.testing as npt
import numpy as np
from scipy.lib.six import xrange

from scipy import stats
from common_tests import (check_normalization, check_moment, check_mean_expect,
        check_var_expect, check_skew_expect, check_kurt_expect,
        check_entropy, check_private_entropy, check_edge_support,
        check_named_args)
knf = npt.dec.knownfailureif

distdiscrete = [
    ['bernoulli',(0.3,)],
    ['binom', (5, 0.4)],
    ['boltzmann',(1.4, 19)],
    ['dlaplace', (0.8,)],  # 0.5
    ['geom', (0.5,)],
    ['hypergeom',(30, 12, 6)],
    ['hypergeom',(21,3,12)],  # numpy.random (3,18,12) numpy ticket:921
    ['hypergeom',(21,18,11)],  # numpy.random (18,3,11) numpy ticket:921
    ['logser', (0.6,)],  # reenabled, numpy ticket:921
    ['nbinom', (5, 0.5)],
    ['nbinom', (0.4, 0.4)],  # from tickets: 583
    ['planck', (0.51,)],   # 4.1
    ['poisson', (0.6,)],
    ['randint', (7, 31)],
    ['skellam', (15, 8)],
    ['zipf', (6.5,)]
]


def test_discrete_basic():
    for distname, arg in distdiscrete:
        distfn = getattr(stats, distname)
        np.random.seed(9765456)
        rvs = distfn.rvs(size=2000, *arg)
        supp = np.unique(rvs)
        m, v = distfn.stats(*arg)
        yield check_cdf_ppf, distfn, arg, supp, distname + ' cdf_ppf'

        cond = distname == 'skellam'
        yield knf(cond, 'ncx2 accuracy')(check_pmf_cdf), distfn, arg,\
                distname + ' pmf_cdf'
        yield check_oth, distfn, arg, distname + ' oth'
        yield check_edge_support, distfn, arg

        alpha = 0.01
        yield check_discrete_chisquare, distfn, arg, rvs, alpha, \
                      distname + ' chisquare'

    seen = set()
    for distname, arg in distdiscrete:
        if distname in seen:
            continue
        seen.add(distname)
        distfn = getattr(stats,distname)
        locscale_defaults = (0,)
        meths = [distfn.pmf, distfn.logpmf, distfn.cdf, distfn.logcdf,
                 distfn.logsf]
        # make sure arguments are within support
        spec_k = {'randint': 11, 'hypergeom': 4, 'bernoulli': 0, }
        k = spec_k.get(distname, 1)
        yield check_named_args, distfn, k, arg, locscale_defaults, meths
        yield check_scale_docstring, distfn

        # Entropy
        yield check_entropy, distfn, arg, distname
        if distfn.__class__._entropy != stats.rv_discrete._entropy:
            yield check_private_entropy, distfn, arg, stats.rv_discrete


def test_moments():
    for distname, arg in distdiscrete:
        distfn = getattr(stats,distname)
        m, v, s, k = distfn.stats(*arg, moments='mvsk')
        yield check_normalization, distfn, arg, distname

        # compare `stats` and `moment` methods
        yield check_moment, distfn, arg, m, v, distname
        yield check_mean_expect, distfn, arg, m, distname
        yield check_var_expect, distfn, arg, m, v, distname
        yield check_skew_expect, distfn, arg, m, v, s, distname

        cond = distname in ['zipf']
        msg = distname + ' fails kurtosis'
        yield knf(cond, msg)(check_kurt_expect), distfn, arg, m, v, k, distname

        # frozen distr moments
        yield check_moment_frozen, distfn, arg, m, 1
        yield check_moment_frozen, distfn, arg, v+m*m, 2


def check_cdf_ppf(distfn, arg, supp, msg):
    # cdf is a step function, and ppf(q) = min{k : cdf(k) >= q, k integer}
    npt.assert_array_equal(distfn.ppf(distfn.cdf(supp, *arg), *arg),
                           supp, msg + '-roundtrip')
    npt.assert_array_equal(distfn.ppf(distfn.cdf(supp, *arg) - 1e-8, *arg),
                           supp, msg + '-roundtrip')
    supp1 = supp[supp < distfn.b]
    npt.assert_array_equal(distfn.ppf(distfn.cdf(supp1, *arg) + 1e-8, *arg),
                     supp1 + distfn.inc, msg + 'ppf-cdf-next')
    # -1e-8 could cause an error if pmf < 1e-8


def check_pmf_cdf(distfn, arg, msg):
    startind = np.int(distfn.ppf(0.01, *arg) - 1)
    index = list(range(startind, startind + 10))
    cdfs, pmfs_cum = distfn.cdf(index,*arg), distfn.pmf(index, *arg).cumsum()
    npt.assert_allclose(cdfs - cdfs[0], pmfs_cum - pmfs_cum[0],
            atol=1e-10, rtol=1e-10)


def check_moment_frozen(distfn, arg, m, k):
    npt.assert_allclose(distfn(*arg).moment(k), m,
            atol=1e-10, rtol=1e-10)


def check_oth(distfn, arg, msg):
    # checking other methods of distfn
    meanint = round(float(distfn.stats(*arg)[0]))  # closest integer to mean
    npt.assert_almost_equal(distfn.sf(meanint, *arg), 1 -
                            distfn.cdf(meanint, *arg), decimal=8)
    median_sf = distfn.isf(0.5, *arg)

    npt.assert_(distfn.sf(median_sf - 1, *arg) > 0.5)
    npt.assert_(distfn.cdf(median_sf + 1, *arg) > 0.5)
    npt.assert_equal(distfn.isf(0.5, *arg), distfn.ppf(0.5, *arg))


def check_discrete_chisquare(distfn, arg, rvs, alpha, msg):
    """Perform chisquare test for random sample of a discrete distribution

    Parameters
    ----------
    distname : string
        name of distribution function
    arg : sequence
        parameters of distribution
    alpha : float
        significance level, threshold for p-value

    Returns
    -------
    result : bool
        0 if test passes, 1 if test fails

    uses global variable debug for printing results

    """
    n = len(rvs)
    nsupp = 20
    wsupp = 1.0/nsupp

    # construct intervals with minimum mass 1/nsupp
    # intervals are left-half-open as in a cdf difference
    distsupport = xrange(max(distfn.a, -1000), min(distfn.b, 1000) + 1)
    last = 0
    distsupp = [max(distfn.a, -1000)]
    distmass = []
    for ii in distsupport:
        current = distfn.cdf(ii,*arg)
        if current - last >= wsupp-1e-14:
            distsupp.append(ii)
            distmass.append(current - last)
            last = current
            if current > (1-wsupp):
                break
    if distsupp[-1] < distfn.b:
        distsupp.append(distfn.b)
        distmass.append(1-last)
    distsupp = np.array(distsupp)
    distmass = np.array(distmass)

    # convert intervals to right-half-open as required by histogram
    histsupp = distsupp+1e-8
    histsupp[0] = distfn.a

    # find sample frequencies and perform chisquare test
    freq,hsupp = np.histogram(rvs,histsupp)
    cdfs = distfn.cdf(distsupp,*arg)
    (chis,pval) = stats.chisquare(np.array(freq),n*distmass)

    npt.assert_(pval > alpha, 'chisquare - test for %s'
           ' at arg = %s with pval = %s' % (msg,str(arg),str(pval)))


def check_scale_docstring(distfn):
    if distfn.__doc__ is not None:
        # Docstrings can be stripped if interpreter is run with -OO
        npt.assert_('scale' not in distfn.__doc__)


if __name__ == "__main__":
    npt.run_module_suite()
