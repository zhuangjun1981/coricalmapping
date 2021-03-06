import os
import numpy as np

def load_mmap(fpath):
    """
    load standard .mmap file generated by caiman
    :param fpath:
    :return: np.array
    """

    fdir, fn = os.path.split(fpath)

    if fn[-5:] != '.mmap':
        raise ValueError('input path: {} is not an .mmap file.'.format(fpath))

    fn_parts = fn.split('_')
    d1 = int(fn_parts[fn_parts.index('d1') + 1])  # column, x
    d2 = int(fn_parts[fn_parts.index('d2') + 1])  # row, y
    d3 = int(fn_parts[fn_parts.index('d3') + 1])  # channel
    d4 = int(fn_parts[fn_parts.index('frames') + 1])  # frame, T
    order = fn_parts[fn_parts.index('order') + 1]

    mov = np.memmap(filename=fpath, shape=(d1, d2, d4), order=order, dtype=np.float32, mode='r')
    mov = mov.transpose((2, 0, 1))

    return mov
