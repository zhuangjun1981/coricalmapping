import numpy as np
import scipy.ndimage as ni


def interpolate_nans(arr):
    """
    fill the nans in a 1d array by interpolating value on both sides
    """

    if len(arr.shape) != 1:
        raise ValueError('input arr should be 1d array.')

    nan_ind = np.isnan(arr)

    nan_pos = nan_ind.nonzero()[0]
    # print(nan_pos)
    data_pos = (~nan_ind).nonzero()[0]
    # print(data_pos)
    data = arr[~nan_ind]
    # print(data)

    arr1 = np.array(arr)
    arr1[nan_ind] = np.interp(nan_pos, data_pos, data)

    return arr1


def downsample(arr, rate, method=np.mean):
    """
    down sample a 1d array by the method

    :param arr: 1d array.
    :param rate: int, larger than 1, downsample rate
    :param method: function that can be applied to one axis of a 2d array
    :return: 1d array downsampled data
    """

    if len(arr.shape) != 1:
        raise ValueError('input arr should be 1d array.')

    rate_int = int(np.round(rate))

    if rate_int < 2:
        raise ValueError('input rate should be a integer larger than 1.')

    if arr.shape[0] < rate_int:
        return np.array([])
    else:
        n_d = arr.shape[0] // rate
        arr_reshape = arr[0: n_d * rate].reshape((n_d, rate))
        arr_d = method(arr_reshape, axis=1)

    return arr_d


def get_pupil_area(pupil_shapes, fs, ell_thr=0.5, median_win=3.):
    """
    from elliptic pupil shapes, calculate pupil areas and filter out outliers.

    step 1: calculate area
    step 2: nan the shape with ellipticity larger than ell_thr
            ellipticity = (a - b) / b
    step 3: interpolate the nans
    step 4: median filter with length of median_win

    :param pupil_shapes: 2d array, each row: each sampling point; column0: axis0; column1: axis1; column2: angle
    :param fs: float, Hz, sampling rate
    :param ell_thr: float, (0. 1.], threshold for ellipticity
    :param median_win: float, sec, window length of median filter

    :return: 1d array of pupil area.
    """

    if len(pupil_shapes.shape) != 2:
        raise ValueError('input pupil_shapes should be 2d array.')

    if pupil_shapes.shape[1] < 2:
        raise ValueError('input pupil_shapes should have at least 2 columns.')

    area = np.pi * pupil_shapes[:, 0] * pupil_shapes[:, 1]
    ax1 = np.nanmax(pupil_shapes[:, 0:2], axis=1)
    ax2 = np.nanmin(pupil_shapes[:, 0:2], axis=1)
    ell = (ax1 - ax2) / ax1
    area[ell > ell_thr] = np.nan
    area = interpolate_nans(area)
    area = ni.median_filter(area, int(fs * median_win))

    return area


def get_running_speed(sig, ts, ref=None, disk_radius=8., fs_final=30., speed_thr_pos=100., speed_thr_neg=-20.,
                      gauss_sig=1.):
    """
    get downsampled and filtered running speed from raw data.

    the sig/ref defines the running disk angle position.

    :param sig: 1d array, voltage, signal from encoder
    :param ts: 1d array, timestamps
    :param ref: 1d array or None, reference from encoder, if None, assuming 5 vol.
    :param disk_radius: float, mouse running disk radius in cm
    :param fs_final: float, the final sampling rate after downsampling
    :param speed_thr_pos: float, cm/sec, positive speed threshold
    :param speed_thr_neg: float, cm/sec, negative speed threshold
    :param gauss_sig: float, sec, gaussian filter sigma
    :return speed: 1d array, downsampled and filtered speed, cm/sec
    :return speed_ts: 1d array, timestamps of speed
    """

    if ref is not None:
        running = 2 * np.pi * (sig / ref) * disk_radius
    else:
        running = 2 * np.pi * (sig / 5.) * disk_radius

    fs_raw = 1. / np.mean(np.diff(ts))

    rate_d = int(fs_raw / fs_final)
    running_d = downsample(arr=running, rate=rate_d, method=np.mean)
    ts_d = downsample(arr=ts, rate=rate_d, method=np.mean)

    speed = np.diff(running_d)

    speed_ts = ts_d[0:-1]
    speed = speed / np.mean(np.diff(speed_ts))

    speed[speed > speed_thr_pos] = np.nan
    speed[speed < speed_thr_neg] = np.nan

    speed = interpolate_nans(speed)

    sigma_pt = int(gauss_sig / np.mean(np.diff(speed_ts)))
    speed = ni.gaussian_filter1d(input=speed, sigma=sigma_pt)

    return speed, speed_ts


if __name__ == '__main__':

    # ============================================================================================================
    y = np.array([1, 1, 1, np.nan, np.nan, 2, 2, np.nan, 0])
    y1 = interpolate_nans(y)
    print(y1)
    # ============================================================================================================