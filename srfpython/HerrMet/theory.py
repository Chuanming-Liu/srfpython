from srfpython.standalone.multipro8 import Job, MapSync
from srfpython.standalone.stdout import waitbar
from srfpython.Herrmann.Herrmann import HerrmannCallerFromLists
from parameterizers import Parameterizer
from datacoders import Datacoder
import numpy as np

"""
Parameterizer : object to convert an array of parameters into smth that can be understood by Herrmann.dispersion
Theory        : object to convert a model array into a data array
Datacoder     : object to convert output from Herrmann.dispersion to an array of data
                          a model array (m)                        
  |                          ^    |
  |                          |    |
  |      mod96file ----->  parameterizer   --------> m_apr, CM
  |      (apriori)           |    |
  |                          |    v
  |                        depth model 
  |                     (ztop, vp, vs, rh)
  |                            |
 theory                  Herrmann.HerrmannCaller.disperse
 (forward problem)             |
  |                            v
  |                       dispersion data 
  |                      (waves, types, modes, freqs, values, (dvalues))
  |                          ^    |
  |                          |    |
  |     surf96file ----->   datacoder      --------> d_obs, CD => logRHOD
  |      (target)            |    |
  v                          |    v
                          a data array (d)
"""


class Theory(object):

    def __init__(self, parameterizer, datacoder, h=0.005, ddc=0.005):
        assert isinstance(parameterizer, Parameterizer)
        assert isinstance(datacoder, Datacoder)
        self.parameterizer, self.datacoder = parameterizer, datacoder

        self.herrmanncaller = HerrmannCallerFromLists(
            waves=datacoder.waves, types=datacoder.types,
            modes=datacoder.modes, freqs=datacoder.freqs,
            h=h, ddc=ddc)

    def __call__(self, m):
        """solves the forward problem"""

        # recover model from parameterized array (m)
        ztop, vp, vs, rh = self.parameterizer.inv(m)

        # call Herrmann's codes
        values = self.herrmanncaller.disperse(ztop, vp, vs, rh)

        # convert and return dispersion data to coded array (d)
        return self.datacoder(values)


class _OverdispCore(object):
    def __init__(self, herrmanncaller):
        self.herrmanncaller = herrmanncaller

    def __call__(self, mms):
        ztop, vp, vs, rh = mms
        try:
            overvalues = self.herrmanncaller.dispersion(ztop, vp, vs, rh)

        except KeyboardInterrupt:
            raise

        except Exception:
            h = ztop[1:] - ztop[:-1]
            # assume failure was caused by rounding issues
            h[h <= 0.001] = 0.001001
            ztop = np.concatenate(([0.], h.cumsum()))
            try:  # again
                overvalues = self.herrmanncaller.disperse(ztop, vp, vs, rh)

            except KeyboardInterrupt:
                raise

            except Exception:
                raise
                overvalues = np.nan * np.ones(len(overwaves))

        return mms, overvalues


def overdisp(ms, overwaves, overtypes, overmodes, overfreqs, verbose=True, **mapkwargs):
    """extrapolate dispersion curves"""

    herrmanncaller = HerrmannCallerFromLists(
        waves=overwaves, types=overtypes,
        modes=overmodes, freqs=overfreqs,
        h=0.005, ddc=0.005)

    fun = _OverdispCore(herrmanncaller)
    gen = (Job(mms) for mms in ms)

    with MapSync(fun, gen, **mapkwargs) as ma:
        if verbose: wb = waitbar('overdisp')
        Njobs = len(ms) - 1.
        for jobid, (mms, overvalues), _, _ in ma:
            if verbose: wb.refresh(jobid / Njobs)
            dds = (overwaves, overtypes, overmodes, overfreqs, overvalues)
            yield mms, dds
        if verbose:
            wb.close()
            print
    print
