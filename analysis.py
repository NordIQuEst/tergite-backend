# This code is part of Tergite
#
# (C) Copyright Abdullah Al Amin 2022
# (C) Copyright David Wahlstedt 2022
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

from typing import Dict, List

import Labber
import matplotlib.pyplot as plt
import numpy as np
import qtanalysis.utilities as qu
import scipy.signal
from resonator_tools import circuit
from scipy.optimize import curve_fit

import settings

POSTPROC_PLOTTING = settings.POSTPROC_PLOTTING


def find_resonators(labber_logfile: Labber.LogFile) -> List[List[float]]:

    # Labber api function, y value is not used scince it is not well defined, for
    # multiple y traces, y represents only the last one, not usable in this case
    # only x value is used for sweeped frequency array
    x, y = labber_logfile.getTraceXY()

    # Extracting data using qtl-analysis repo, xdict contains third dimension of
    # data, for example sweeped power values, ydict contains values of the traces

    xdict, ydict = qu.file_handling.LabberParsing(labber_logfile)
    result = extract_resonance_frequencies(x, y, xdict, ydict)
    print("\n")
    for i_sweep in range(len(result)):
        print(f"Number or resonators, sweep {i_sweep}: {len(result[i_sweep])}")

    for key in xdict.keys():
        print(f"Number of traces for {key}: {len(xdict[key]['values'])}")
        print(f"Corresponding power: {xdict[key]['values']}")
    print(f"Resonance frequencies: {result}")
    print("\n")
    return result


# Processing results for resonators resonace frequencies
# algorithm for approximate peak detection is not robust
# may fail in some measurement/traces, improvement required.
# parameter y and xdict is not used, passed for possible
# future uses.
def extract_resonance_frequencies(x, y, xdict, ydict) -> List[List[float]]:
    resonance_frequencies = []
    for _idx, trace in enumerate(ydict["y0"]["values"]):
        abs_trace = np.absolute(trace)
        # Detrain the trace using scipy.signal
        abs_trace = scipy.signal.detrend(
            abs_trace, axis=-1, type="linear", bp=0, overwrite_data=False
        )
        # Filter noise to smooth the trace, second parameter in the
        # savgol_filter needs to be odd, higher value of it results in
        # more smothing, but at the cost of reducing resosnance dip
        abs_trace = scipy.signal.savgol_filter(abs_trace, 11, 2)
        # Used for defining peak detection criterion
        mean = np.mean(abs_trace)
        std = np.std(abs_trace)
        # FIXME: Quick hard coded solution, improvment required
        min_height = -3 * std - mean
        # Detecting the possible and approximate pick or dips
        peaks, _ = scipy.signal.find_peaks(-abs_trace, height=-min_height, distance=100)
        # Extracting the frequiencies of the peaks
        peak_frequencies = x[peaks]
        # Each list in the resonance_frequencies list represents
        # corresponding resonanace frequiencies of the current trace
        resonance_frequencies.append(peak_frequencies.tolist())

    return resonance_frequencies


# fits resonators in traces from the given index list itraces
def fit_resonator_itraces(
    labber_logfile: Labber.LogFile, itraces: List[int]
) -> List[float]:

    x, y = labber_logfile.getTraceXY()

    xdict, ydict = qu.file_handling.LabberParsing(labber_logfile)

    results = []

    for itrace in itraces:
        trace = ydict["y0"]["values"][itrace]
        port1 = circuit.notch_port(x, trace)
        port1.autofit()
        results += [port1.fitresults]
        if POSTPROC_PLOTTING:
            port1.plotall()

    return results


# gaussian fits in traces from the given index list itraces
def gaussian_fit_itraces(
    labber_logfile: Labber.LogFile, itraces: List[int]
) -> List[float]:

    xdict, ydict = qu.file_handling.LabberParsing(labber_logfile)

    results = []

    def gauss(x, H, A, x0, sigma):
        return H + A * np.exp(-((x - x0) ** 2) / (2 * sigma**2))

    def gauss_fit(x, y):
        mean = sum(x * y) / sum(y)
        sigma = np.sqrt(sum(y * (x - mean) ** 2) / sum(y))
        popt, pcov = curve_fit(gauss, x, y, p0=[min(y), max(y), mean, sigma])
        return popt

    # itraces are indices of the traces for multiple recordings in the same log
    for itrace in itraces:
        frequency_array = xdict["x0"]["values"]
        abs_trace = np.absolute(ydict["y0"]["values"][itrace])

        H, A, x0, sigma = gauss_fit(frequency_array, abs_trace)
        FWHM = 2.35482 * sigma

        print("The offset of the gaussian baseline is", H)
        print("The center of the gaussian fit is", x0)
        print("The sigma of the gaussian fit is", sigma)
        print("The maximum intensity of the gaussian fit is", H + A)
        print("The Amplitude of the gaussian fit is", A)
        print("The FWHM of the gaussian fit is", FWHM)

        fitted_data = gauss(frequency_array, *gauss_fit(frequency_array, abs_trace))

        results += [x0]

        if POSTPROC_PLOTTING:
            # plotting of the fitting, may be useful later
            plt.plot(frequency_array, abs_trace, "--b", label="orginal data")
            plt.plot(frequency_array, fitted_data, "-r", label="fit")
            plt.legend()
            plt.title("Gaussian fit,  $f(x) = A e^{(-(x-x_0)^2/(2sigma^2))}$")
            plt.xlabel("Frequency (Hz)")
            plt.ylabel("Amplitude (V)")
            plt.show()

    return results


# fits oscillation in traces from the given index list itraces
def fit_oscillation_itraces(
    labber_logfile: Labber.LogFile, itraces: List[int]
) -> List[Dict[str, float]]:

    xdict, ydict = qu.file_handling.LabberParsing(labber_logfile)

    results = []

    def fit_sin(x, y):
        ff = np.fft.fftfreq(len(x), (x[1] - x[0]))  # assume uniform spacing
        ffy = abs(np.fft.fft(y))
        guess_frequency = abs(
            ff[np.argmax(ffy[1:]) + 1]
        )  # excluding the zero frequency "peak", which is related to offset
        guess_amp = np.std(y) * 2.0**0.5
        guess_offset = np.mean(y)
        guess = np.array([guess_amp, 2.0 * np.pi * guess_frequency, 0.0, guess_offset])

        def sinfunc(t, A, w, p, c):
            return A * np.sin(w * t + p) + c

        popt, pcov = scipy.optimize.curve_fit(sinfunc, x, y, p0=guess)
        A, w, p, c = popt
        f = w / (2.0 * np.pi)
        fitfunc = lambda t: A * np.sin(w * t + p) + c
        return {
            "amp": A,
            "omega": w,
            "phase": p,
            "offset": c,
            "freq": f,
            "period": 1.0 / f,
            "fitfunc": fitfunc,
            "maxcov": np.max(pcov),
            "rawres": (guess, popt, pcov),
        }

    # itraces are indices of the traces for multiple recordings in the same log
    for itrace in itraces:
        frequency_array = xdict["x0"]["values"]
        abs_trace = np.absolute(ydict["y0"]["values"][itrace])
        result = fit_sin(frequency_array, abs_trace)
        # In case of Rabi, the period is the inverted the frequency
        results += [result]
        print(
            "Amplitude=%(amp)s, freq=%(freq)s, period.=%(period)s, Angular freq.=%(omega)s, phase=%(phase)s, offset=%(offset)s, Max. Cov.=%(maxcov)s"
            % result
        )

        if POSTPROC_PLOTTING:
            plt.plot(frequency_array, abs_trace, "-k", label="y", linewidth=2)
            plt.plot(
                frequency_array,
                result["fitfunc"](frequency_array),
                "r-",
                label="y fit curve",
                linewidth=2,
            )
            plt.show()

    return results
