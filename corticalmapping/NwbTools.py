import os
import numpy as np
import h5py
import corticalmapping.ephys.OpenEphysWrapper as oew
import corticalmapping.ephys.KilosortWrapper as kw
import corticalmapping.HighLevel as hl
import corticalmapping.core.FileTools as ft
import corticalmapping.core.TimingAnalysis as ta
import corticalmapping.core.PlottingTools as pt
try:
    from nwb.nwb import NWB
except ImportError:
    print 'no Allen Institute NWB API. get this from ' \
          'http://stimash.corp.alleninstitute.org/projects/INF/repos/ainwb/browse'

DEFAULT_GENERAL = {
                   'session_id': '',
                   'experimenter': '',
                   'institution': 'Allen Institute for Brain Science',
                   # 'lab': '',
                   # 'related_publications': '',
                   'notes': '',
                   'experiment_description': '',
                   # 'data_collection': '',
                   'stimulus': '',
                   # 'pharmacology': '',
                   # 'surgery': '',
                   # 'protocol': '',
                   'subject': {
                               'subject_id': '',
                               # 'description': '',
                               'species': 'Mus musculus',
                               'genotype': '',
                               'sex': '',
                               'age': '',
                               # 'weight': '',
                               },
                   # 'virus': '',
                   # 'slices': '',
                   'extracellular_ephys': {
                                           'electrode_map': '',
                                           'sampling_rate': 30000.,
                                           # 'electrode_group': [],
                                           # 'impedance': [],
                                           # 'filtering': []
                                           },
                   'optophysiology': {
                                      'indicator': '',
                                      # 'excitation_lambda': '',
                                      'imaging_rate': '',
                                      # 'location': '',
                                      # 'device': '',
                                      },
                   # 'optogenetics': {},
                   'devices': {}
                   }


class RecordedFile(NWB):
    """
    Jun's wrapper of nwb file. Designed for LGN-ephys/V1-ophys dual recording experiments. Should be able to save
    ephys, wide field, 2-photon data in a single file.
    """

    def __init__(self, filename, is_manual_check=False, **kwargs):

        if os.path.isfile(filename):
            if is_manual_check:
                keyboard_input = ''
                while keyboard_input != 'y' and keyboard_input != 'n':
                    keyboard_input = raw_input('\nthe path "' + filename + '" already exists. Modify it? (y/n) \n')
                    if keyboard_input == 'y':
                        super(RecordedFile, self).__init__(filename=filename, modify=True, **kwargs)
                    elif keyboard_input == 'n':
                        raise IOError('file already exists.')
            else:
                print('\nModifying existing nwb file: ' + filename)
                super(RecordedFile, self).__init__(filename=filename, modify=True, **kwargs)
        else:
            print('\nCreating a new nwb file: ' + filename)
            super(RecordedFile, self).__init__(filename=filename, modify=False, **kwargs)

    def add_general(self, general=DEFAULT_GENERAL, is_overwrite=True):
        """
        add general dictionary to the general filed
        """
        slf = self.file_pointer

        for key, value in general.items():
            if isinstance(value, dict):
                try:
                    curr_group = slf['general'].create_group(key)
                except ValueError:
                    curr_group = slf['general'][key]
                for key2, value2 in value.items():
                    ft.update_key(curr_group, key2, value2, is_overwrite=is_overwrite)
            else:
                ft.update_key(slf['general'], key, value, is_overwrite=is_overwrite)

    def add_open_ephys_data(self, folder, prefix, digital_channels=()):
        """
        add open ephys raw data to self, in acquisition group, less useful, because the digital events needs to be
        processed before added in
        :param folder: str, the folder contains open ephys raw data
        :param prefix: str, prefix of open ephys files
        :param digital_channels: list of str, digital channel
        :return:
        """
        output = oew.pack_folder_for_nwb(folder=folder, prefix=prefix, digital_channels=digital_channels)

        for key, value in output.items():

            if 'CH' in key:  # analog channel for electrode recording
                ch_ind = int(key[key.find('CH') + 2:])
                ch_name = 'ch_' + ft.int2str(ch_ind, 4)
                ch_trace = value['trace']
                ch_series = self.create_timeseries('ElectricalSeries', ch_name, 'acquisition')
                ch_series.set_data(ch_trace, unit='bit', conversion=float(value['header']['bitVolts']),
                                   resolution=1.)
                ch_series.set_time_by_rate(time_zero=0.0,  # value['header']['start_time'],
                                           rate=float(value['header']['sampleRate']))
                ch_series.set_value('electrode_idx', ch_ind)
                ch_series.set_value('num_samples', len(ch_trace))
                ch_series.set_comments('continuous')
                ch_series.set_description('extracellular continuous voltage recording from tetrode')
                ch_series.set_source('open ephys')
                ch_series.finalize()

            elif key != 'events':  # other continuous channels
                ch_name = key[len(prefix) + 1:]
                ch_trace = value['trace']
                ch_series = self.create_timeseries('AbstractFeatureSeries', ch_name, 'acquisition')
                ch_series.set_data(ch_trace, unit='bit', conversion=float(value['header']['bitVolts']),
                                   resolution=1.)
                ch_series.set_time_by_rate(time_zero=0.0,  # value['header']['start_time'],
                                           rate=float(value['header']['sampleRate']))
                ch_series.set_value('features', ch_name)
                ch_series.set_value('feature_units', 'bit')
                ch_series.set_value('num_samples', len(ch_trace))
                ch_series.set_value('help', 'continuously recorded analog channels with same sampling times as '
                                            'of electrode recordings')
                ch_series.set_comments('continuous')
                ch_series.set_description('continuous voltage recording from IO board')
                ch_series.set_source('open ephys')
                ch_series.finalize()

            else:  # digital events

                for key2, value2 in value.items():

                    ch_rise_ts = value2['rise']
                    ch_series_rise = self.create_timeseries('TimeSeries', key2+'_rise', 'acquisition')
                    ch_series_rise.set_data([], unit='', conversion=np.nan, resolution=np.nan)
                    if len(ch_rise_ts) == 0:
                        ch_rise_ts = np.array([np.nan])
                        ch_series_rise.set_time(ch_rise_ts)
                        ch_series_rise.set_value('num_samples', 0)
                    else:
                        ch_series_rise.set_time(ch_rise_ts)
                    ch_series_rise.set_description('timestamps of rise cross of digital channel: ' + key2)
                    ch_series_rise.set_source('open ephys')
                    ch_series_rise.set_comments('digital')
                    ch_series_rise.finalize()

                    ch_fall_ts = value2['fall']
                    ch_series_fall = self.create_timeseries('TimeSeries', key2 + '_fall', 'acquisition')
                    ch_series_fall.set_data([], unit='', conversion=np.nan, resolution=np.nan)
                    if len(ch_fall_ts) == 0:
                        ch_fall_ts = np.array([np.nan])
                        ch_series_fall.set_time(ch_fall_ts)
                        ch_series_fall.set_value('num_samples', 0)
                    else:
                        ch_series_fall.set_time(ch_fall_ts)
                    ch_series_fall.set_description('timestamps of fall cross of digital channel: ' + key2)
                    ch_series_fall.set_source('open ephys')
                    ch_series_fall.set_comments('digital')
                    ch_series_fall.finalize()

    def add_open_ephys_continuous_data(self, folder, prefix):
        """
        add open ephys raw continuous data to self, in acquisition group
        :param folder: str, the folder contains open ephys raw data
        :param prefix: str, prefix of open ephys files
        :param digital_channels: list of str, digital channel
        :return:
        """
        output = oew.pack_folder_for_nwb(folder=folder, prefix=prefix)

        for key, value in output.items():

            if 'CH' in key:  # analog channel for electrode recording
                ch_ind = int(key[key.find('CH') + 2:])
                ch_name = 'ch_' + ft.int2str(ch_ind, 4)
                ch_trace = value['trace']
                ch_series = self.create_timeseries('ElectricalSeries', ch_name, 'acquisition')
                ch_series.set_data(ch_trace, unit='bit', conversion=float(value['header']['bitVolts']),
                                   resolution=1.)
                ch_series.set_time_by_rate(time_zero=0.0,  # value['header']['start_time'],
                                           rate=float(value['header']['sampleRate']))
                ch_series.set_value('electrode_idx', ch_ind)
                ch_series.set_value('num_samples', len(ch_trace))
                ch_series.set_comments('continuous')
                ch_series.set_description('extracellular continuous voltage recording from tetrode')
                ch_series.set_source('open ephys')
                ch_series.finalize()

            elif key != 'events':  # other continuous channels
                ch_name = key[len(prefix) + 1:]
                ch_trace = value['trace']
                ch_series = self.create_timeseries('AbstractFeatureSeries', ch_name, 'acquisition')
                ch_series.set_data(ch_trace, unit='bit', conversion=float(value['header']['bitVolts']),
                                   resolution=1.)
                ch_series.set_time_by_rate(time_zero=0.0,  # value['header']['start_time'],
                                           rate=float(value['header']['sampleRate']))
                ch_series.set_value('features', ch_name)
                ch_series.set_value('feature_units', 'bit')
                ch_series.set_value('num_samples', len(ch_trace))
                ch_series.set_value('help', 'continuously recorded analog channels with same sampling times as '
                                            'of electrode recordings')
                ch_series.set_comments('continuous')
                ch_series.set_description('continuous voltage recording from IO board')
                ch_series.set_source('open ephys')
                ch_series.finalize()

    def add_acquisition_image(self, name, img, format='array', description=''):
        """
        add arbitrarily recorded image into acquisition group, mostly surface vasculature image
        :param name:
        :param img:
        :param format:
        :param description:
        :return:
        """
        img_dset = self.file_pointer['acquisition/images'].create_dataset(name, data=img)
        img_dset.attrs['format'] = format
        img_dset.attrs['description'] = description

    def add_acquired_image_series_as_remote_link(self, name, image_file_path, dataset_path, timestamps,
                                                 description='', comments='', data_format='zyx', pixel_size=np.nan,
                                                 pixel_size_unit=''):
        """
        add a required image series in to acquisition field as a link to an external hdf5 file.
        :param name: str, name of the image series
        :param image_file_path: str, the full file system path to the hdf5 file containing the raw image data
        :param dataset_path: str, the path within the hdf5 file pointing to the raw data. the object should have at
                             least 3 attributes: 'conversion', resolution, unit
        :param timestamps: 1-d array, the length of this array should be the same as number of frames in the image data
        :param data_format: str, required field for ImageSeries object
        :param pixel_size: array, size of pixel
        :param pixel_size_unit: str, unit of pixel size
        :return:
        """

        img_file = h5py.File(image_file_path)
        img_data = img_file[dataset_path]
        if timestamps.shape[0] != img_data.shape[0]:
            raise ValueError('Number of frames does not equal to the length of timestamps!')
        img_series = self.create_timeseries(ts_type='ImageSeries', name=name, modality='acquisition')
        img_series.set_data_as_remote_link(image_file_path, dataset_path)
        img_series.set_time(timestamps)
        img_series.set_description(description)
        img_series.set_comments(comments)
        img_series.set_value('bits_per_pixel', img_data.dtype.itemsize * 8)
        img_series.set_value('format', data_format)
        img_series.set_value('dimension', img_data.shape)
        img_series.set_value('image_file_path', image_file_path)
        img_series.set_value('image_data_path_within_file', dataset_path)
        img_series.set_value('pixel_size', pixel_size)
        img_series.set_value('pixel_size_unit', pixel_size_unit)
        img_series.finalize()

    def add_phy_template_clusters(self, folder, module_name, ind_start=None, ind_end=None, is_merge_units=False,
                                  is_add_artificial_unit=False, artificial_unit_firing_rate=2.):
        """
        extract phy-template clustering results to nwb format. Only extract spike times, no template for now.
        Usually the continuous channels of multiple files are concatenated for kilosort. ind_start and ind_end are
        Used to extract the data of this particular file.

        :param folder: folder containing phy template results.
                       expects cluster_groups.csv, spike_clusters.npy and spike_times.npy in the folder.
        :param module_name: str, name of clustering module group
        :param ind_start: int, the start index of continuous channel of the current file in the concatenated file.
        :param ind_end: int, the end index of continuous channel of the current file in the concatenated file.
        :param is_merge_units: bool, if True: the unit_mua will include all isolated units and mua
                                     if False: the unit_mua will only include mua
        :param is_add_artificial_unit: bool, if True: a artificial unit with possion event will be added, this unit
                                       will have name 'aua' and refractory period 1 ms.
        :param artificial_unit_firing_rate: float, firing rate of the artificial unit
        :return:
        """

        if ind_start == None:
            ind_start = 0

        if ind_end == None:
            ind_end = self.file_pointer['acquisition/timeseries/photodiode/num_samples'].value

        if ind_start >= ind_end:
            raise ValueError('ind_end should be larger than ind_start.')

        try:
            fs = self.file_pointer['general/extracellular_ephys/sampling_rate'].value
        except KeyError:
            print('\nCannot find "general/extracellular_ephys/sampling_rate" field. Abort process.')
            return

        clusters_path = os.path.join(folder, 'spike_clusters.npy')
        spike_times_path = os.path.join(folder, 'spike_times.npy')
        phy_template_output = kw.get_clusters(kw.read_csv(os.path.join(folder, 'cluster_groups.csv')))

        spike_ind = kw.get_spike_times_indices(phy_template_output, spike_clusters_path=clusters_path,
                                               spike_times_path=spike_times_path)

        # print 'before: ', spike_ind['unit_mua'].shape

        if is_merge_units:
            if 'unit_mua' not in spike_ind.keys():
                spike_ind.update({'unit_mua': []})
            else:
                spike_ind['unit_mua'] = [spike_ind['unit_mua']]

            for unit_name, spks in spike_ind.items():
                if unit_name != 'unit_mua':
                    spike_ind['unit_mua'].append(spks)

            spike_ind['unit_mua'] = np.sort(np.concatenate(spike_ind['unit_mua'], axis=0))
            # print 'type of unit_mua spike ind: ', type(spike_ind['unit_mua'])

        # print 'after: ', spike_ind['unit_mua'].shape

        mod = self.create_module(name=module_name)
        mod.set_description('phy-template manual clustering after kilosort')
        unit_times = mod.create_interface('UnitTimes')
        for unit in spike_ind.keys():
            curr_ts = np.array(spike_ind[unit])
            curr_ts = curr_ts[np.logical_and(curr_ts >= ind_start, curr_ts < ind_end)] - ind_start
            curr_ts = curr_ts / fs
            unit_times.add_unit(unit_name=unit, unit_times=curr_ts,
                                source='electrophysiology extracellular recording',
                                description="Data spike-sorted by: " + self.file_pointer['general/experimenter'].value +
                                            ' using phy-template. Spike time unit: seconds.')

        if is_add_artificial_unit:
            file_length = (ind_end - ind_start) / fs
            au_ts = ta.possion_event_ts(duration=file_length, firing_rate=artificial_unit_firing_rate,
                                        refractory_dur=0.001, is_plot=False)
            unit_times.add_unit(unit_name='unit_aua', unit_times=au_ts,
                                source='electrophysiology extracellular recording',
                                description='Artificial possion unit for control. Spike time unit: seconds.')

        unit_times.finalize()
        mod.finalize()

    def add_external_LFP(self,  traces, fs=30000., module_name=None, notch_base=60., notch_bandwidth=1., notch_harmonics=4,
                         notch_order=2, lowpass_cutoff=300., lowpass_order=5, resolution=0, conversion=0, unit='',
                        comments='', source=''):
        """
        add LFP of raw arbitrary electrical traces into LFP module into /procession field. the trace will be filtered
        by corticalmapping.HighLevel.get_lfp() function. All filters are butterworth digital filters

        :param module_name: str, name of module to be added
        :param traces: dict, {str: 1d-array}, {name: trace}, input raw traces
        :param fs: float, sampling rate, Hz
        :param notch_base: float, Hz, base frequency of powerline contaminating signal
        :param notch_bandwidth: float, Hz, filter bandwidth at each side of center frequency
        :param notch_harmonics: int, number of harmonics to filter out
        :param notch_order: int, order of butterworth bandpass notch filter, for a narrow band, shouldn't be larger than 2
        :param lowpass_cutoff: float, Hz, cutoff frequency of lowpass filter
        :param lowpass_order: int, order of butterworth lowpass filter
        :param resolution: float, resolution of LFP time series
        :param conversion: float, conversion of LFP time series
        :param unit: str, unit of LFP time series
        :param comments: str, interface comments
        :param source: str, interface source
        """

        if module_name is None or module_name=='':
            module_name = 'external_LFP'

        lfp = {}
        for tn, trace in traces.items():
            curr_lfp = hl.get_lfp(trace,fs=fs, notch_base=notch_base, notch_bandwidth=notch_bandwidth,
                                  notch_harmonics=notch_harmonics, notch_order=notch_order,
                                  lowpass_cutoff=lowpass_cutoff, lowpass_order=lowpass_order)
            lfp.update({tn: curr_lfp})

        lfp_mod = self.create_module(module_name)
        lfp_mod.set_description('LFP from external traces')
        lfp_interface = lfp_mod.create_interface('LFP')
        lfp_interface.set_value('description', 'LFP of raw arbitrary electrical traces. The traces were filtered by '
                                'corticalmapping.HighLevel.get_lfp() function. First, the powerline contamination at '
                                'multiplt harmonics were filtered out by a notch filter. Then the resulting traces were'
                                ' filtered by a lowpass filter. All filters are butterworth digital filters')
        lfp_interface.set_value('comments', comments)
        lfp_interface.set_value('notch_base', notch_base)
        lfp_interface.set_value('notch_bandwidth', notch_bandwidth)
        lfp_interface.set_value('notch_harmonics', notch_harmonics)
        lfp_interface.set_value('notch_order', notch_order)
        lfp_interface.set_value('lowpass_cutoff', lowpass_cutoff)
        lfp_interface.set_value('lowpass_order', lowpass_order)
        lfp_interface.set_source(source)
        for tn, t_lfp in lfp.items():
            curr_ts = self.create_timeseries('ElectricalSeries', tn, modality='other')
            curr_ts.set_data(t_lfp, conversion=conversion, resolution=resolution, unit=unit)
            curr_ts.set_time_by_rate(time_zero=0., rate=fs)
            curr_ts.set_value('num_samples', len(t_lfp))
            curr_ts.set_value('electrode_idx', 0)
            lfp_interface.add_timeseries(curr_ts)
            lfp_interface.finalize()

        lfp_mod.finalize()

    def add_internal_LFP(self, continuous_channels, module_name=None, notch_base=60., notch_bandwidth=1.,
                         notch_harmonics=4, notch_order=2, lowpass_cutoff=300., lowpass_order=5, comments='',
                         source=''):
        """
        add LFP of acquired electrical traces into LFP module into /procession field. the trace will be filtered
        by corticalmapping.HighLevel.get_lfp() function. All filters are butterworth digital filters.

        :param continuous_channels: list of strs, name of continuous channels saved in '/acquisition/timeseries'
                                    folder, the time axis of these channels should be saved by rate
                                    (ephys sampling rate).
        :param module_name: str, name of module to be added
        :param notch_base: float, Hz, base frequency of powerline contaminating signal
        :param notch_bandwidth: float, Hz, filter bandwidth at each side of center frequency
        :param notch_harmonics: int, number of harmonics to filter out
        :param notch_order: int, order of butterworth bandpass notch filter, for a narrow band, shouldn't be larger than 2
        :param lowpass_cutoff: float, Hz, cutoff frequency of lowpass filter
        :param lowpass_order: int, order of butterworth lowpass filter
        :param comments: str, interface comments
        :param source: str, interface source
        """

        if module_name is None or module_name=='':
            module_name = 'LFP'

        lfp_mod = self.create_module(module_name)
        lfp_mod.set_description('LFP from acquired electrical traces')
        lfp_interface = lfp_mod.create_interface('LFP')
        lfp_interface.set_value('description', 'LFP of acquired electrical traces. The traces were filtered by '
                                               'corticalmapping.HighLevel.get_lfp() function. First, the powerline '
                                               'contamination at multiplt harmonics were filtered out by a notch '
                                               'filter. Then the resulting traces were filtered by a lowpass filter. '
                                               'All filters are butterworth digital filters')
        lfp_interface.set_value('comments', comments)
        lfp_interface.set_value('notch_base', notch_base)
        lfp_interface.set_value('notch_bandwidth', notch_bandwidth)
        lfp_interface.set_value('notch_harmonics', notch_harmonics)
        lfp_interface.set_value('notch_order', notch_order)
        lfp_interface.set_value('lowpass_cutoff', lowpass_cutoff)
        lfp_interface.set_value('lowpass_order', lowpass_order)
        lfp_interface.set_source(source)

        for channel in continuous_channels:

            print '\n', channel, ': start adding LFP ...'

            trace = self.file_pointer['acquisition/timeseries'][channel]['data'].value
            fs = self.file_pointer['acquisition/timeseries'][channel]['starting_time'].attrs['rate']
            start_time = self.file_pointer['acquisition/timeseries'][channel]['starting_time'].value
            conversion = self.file_pointer['acquisition/timeseries'][channel]['data'].attrs['conversion']
            resolution = self.file_pointer['acquisition/timeseries'][channel]['data'].attrs['resolution']
            unit = self.file_pointer['acquisition/timeseries'][channel]['data'].attrs['unit']
            ts_source = self.file_pointer['acquisition/timeseries'][channel].attrs['source']

            print channel, ': calculating LFP ...'

            t_lfp = hl.get_lfp(trace, fs=fs, notch_base=notch_base, notch_bandwidth=notch_bandwidth,
                               notch_harmonics=notch_harmonics, notch_order=notch_order, lowpass_cutoff=lowpass_cutoff,
                               lowpass_order=lowpass_order)

            curr_ts = self.create_timeseries('ElectricalSeries', channel, modality='other')
            curr_ts.set_data(t_lfp, conversion=conversion, resolution=resolution, unit=unit)
            curr_ts.set_time_by_rate(time_zero=start_time, rate=fs)
            curr_ts.set_value('num_samples', len(t_lfp))
            curr_ts.set_value('electrode_idx', int(channel.split('_')[1]))
            curr_ts.set_source(ts_source)
            lfp_interface.add_timeseries(curr_ts)
            print channel, ': finished adding LFP.'

        lfp_interface.finalize()

        lfp_mod.finalize()

    def add_visual_stimulation(self, log_path, display_order=0):
        """
        load visual stimulation given saved display log pickle file
        :param log_path: the path to the display log generated by corticalmapping.VisualStim
        :param display_order: int, in case there is more than one visual display in the file.
                              This value records the order of the displays
        :return:
        """
        self._check_display_order(display_order)

        log_dict = ft.loadFile(log_path)

        stim_name = log_dict['stimulation']['stimName']

        display_frames = log_dict['presentation']['displayFrames']
        time_stamps = log_dict['presentation']['timeStamp']

        if len(display_frames) != len(time_stamps):
            print ('\nWarning: {}'.format(log_path))
            print('Unequal number of displayFrames ({}) and timeStamps ({}).'.format(len(display_frames),
                                                                                     len(time_stamps)))

        if stim_name == 'SparseNoise':
            self._add_sparse_noise_stimulation(log_dict, display_order=display_order)
        elif stim_name == 'FlashingCircle':
            self._add_flashing_circle_stimulation(log_dict, display_order=display_order)
        elif stim_name == 'UniformContrast':
            self._add_uniform_contrast_stimulation(log_dict, display_order=display_order)
        elif stim_name == 'DriftingGratingCircle':
            self._add_drifting_grating_circle_stimulation(log_dict, display_order=display_order)
        elif stim_name == 'KSstimAllDir':
            self._add_drifting_checker_board_stimulation(log_dict, display_order=display_order)
        else:
            raise ValueError('stimulation name {} unrecognizable!'.format(stim_name))

    def _add_sparse_noise_stimulation(self, log_dict, display_order):

        stim_name = log_dict['stimulation']['stimName']

        if stim_name != 'SparseNoise':
            raise ValueError('stimulus was not sparse noise.')

        display_frames = log_dict['presentation']['displayFrames']
        time_stamps = log_dict['presentation']['timeStamp']

        frame_array = np.empty((len(display_frames), 5), dtype=np.float32)
        for i, frame in enumerate(display_frames):
            if frame[0] == 0:
                frame_array[i] = np.array([0, np.nan, np.nan, np.nan, frame[3]])
            elif frame[0] == 1:
                frame_array[i] = np.array([1, frame[1][0], frame[1][1], frame[2], frame[3]])
            else:
                raise ValueError('The first value of ' + str(i) + 'th display frame: ' + str(frame) + ' should' + \
                                 ' be only 0 or 1.')
        stim = self.create_timeseries('TimeSeries', ft.int2str(display_order, 2) + '_' + stim_name,
                                      'stimulus')
        stim.set_time(time_stamps)
        stim.set_data(frame_array, unit='', conversion=np.nan, resolution=np.nan)
        stim.set_comments('the timestamps of displayed frames (saved in data) are referenced to the start of'
                          'this particular display, not the master time clock. For more useful timestamps, check'
                          '/processing for aligned photodiode onset timestamps.')
        stim.set_description('data formatting: [isDisplay (0:gap; 1:display), azimuth (deg), altitude (deg), '
                             'polarity (from -1 to 1), indicatorColor (for photodiode, from -1 to 1)]')
        stim.set_value('data_formatting', ['isDisplay', 'azimuth', 'altitude', 'polarity', 'indicatorColor'])
        stim.set_value('background_color', log_dict['stimulation']['background'])
        stim.set_source('corticalmapping.VisualStim.SparseNoise for stimulus; '
                        'corticalmapping.VisualStim.DisplaySequence for display')
        stim.finalize()

    def _add_flashing_circle_stimulation(self, log_dict, display_order):

        stim_name = log_dict['stimulation']['stimName']

        if stim_name != 'FlashingCircle':
            raise ValueError('stimulus should be flashing circle.')

        display_frames = log_dict['presentation']['displayFrames']
        time_stamps = log_dict['presentation']['timeStamp']

        frame_array = np.empty((len(display_frames), 2), dtype=np.int8)
        for i, frame in enumerate(display_frames):
            if frame[0] == 0 or frame[0] == 1:
                frame_array[i] = np.array([frame[0], frame[3]])
            else:
                raise ValueError('The first value of ' + str(i) + 'th display frame: ' + str(frame) + ' should' + \
                                 ' be only 0 or 1.')
        stim = self.create_timeseries('TimeSeries', ft.int2str(display_order, 2) + '_' + stim_name,
                                      'stimulus')
        stim.set_time(time_stamps)
        stim.set_data(frame_array, unit='', conversion=np.nan, resolution=np.nan)
        stim.set_comments('the timestamps of displayed frames (saved in data) are referenced to the start of'
                          'this particular display, not the master time clock. For more useful timestamps, check'
                          '/processing for aligned photodiode onset timestamps.')
        stim.set_description('data formatting: [isDisplay (0:gap; 1:display), '
                             'indicatorColor (for photodiode, from -1 to 1)]')
        stim.set_value('data_formatting', ['isDisplay', 'indicatorColor'])
        stim.set_source('corticalmapping.VisualStim.FlashingCircle for stimulus; '
                        'corticalmapping.VisualStim.DisplaySequence for display')
        stim.set_value('radius_deg', log_dict['stimulation']['radius'])
        stim.set_value('center_location_deg', log_dict['stimulation']['center'])
        stim.set_value('center_location_format', '[azimuth, altitude]')
        stim.set_value('color', log_dict['stimulation']['color'])
        stim.set_value('background_color', log_dict['stimulation']['background'])
        stim.finalize()

    def _add_uniform_contrast_stimulation(self, log_dict, display_order):

        stim_name = log_dict['stimulation']['stimName']

        if stim_name != 'UniformContrast':
            raise ValueError('stimulus should be uniform contrast.')

        display_frames = log_dict['presentation']['displayFrames']
        time_stamps = log_dict['presentation']['timeStamp']

        frame_array = np.array(display_frames, dtype=np.int8)

        stim = self.create_timeseries('TimeSeries', ft.int2str(display_order, 2) + '_' + stim_name,
                                      'stimulus')
        stim.set_time(time_stamps)
        stim.set_data(frame_array, unit='', conversion=np.nan, resolution=np.nan)
        stim.set_comments('the timestamps of displayed frames (saved in data) are referenced to the start of'
                          'this particular display, not the master time clock. For more useful timestamps, check'
                          '/processing for aligned photodiode onset timestamps.')
        stim.set_description('data formatting: [isDisplay (0:gap; 1:display), '
                             'indicatorColor (for photodiode, from -1 to 1)]')
        stim.set_value('data_formatting', ['isDisplay', 'indicatorColor'])
        stim.set_source('corticalmapping.VisualStim.UniformContrast for stimulus; '
                        'corticalmapping.VisualStim.DisplaySequence for display')
        stim.set_value('color', log_dict['stimulation']['color'])
        stim.set_value('background_color', log_dict['stimulation']['background'])
        stim.finalize()

    def _add_drifting_grating_circle_stimulation(self, log_dict, display_order):

        stim_name = log_dict['stimulation']['stimName']

        if stim_name != 'DriftingGratingCircle':
            raise ValueError('stimulus should be drifting grating circle.')

        display_frames = log_dict['presentation']['displayFrames']
        time_stamps = log_dict['presentation']['timeStamp']

        frame_array = np.array(display_frames)
        frame_array[np.equal(frame_array, None)] = np.nan
        frame_array = frame_array.astype(np.float32)

        stim = self.create_timeseries('TimeSeries', ft.int2str(display_order, 2) + '_' + stim_name,
                                      'stimulus')
        stim.set_time(time_stamps)
        stim.set_data(frame_array, unit='', conversion=np.nan, resolution=np.nan)
        stim.set_comments('the timestamps of displayed frames (saved in data) are referenced to the start of'
                          'this particular display, not the master time clock. For more useful timestamps, check'
                          '/processing for aligned photodiode onset timestamps.')
        stim.set_description('data formatting: [isDisplay (0:gap; 1:display), '
                             'firstFrameInCycle (first frame in cycle:1, rest display frames: 0), '
                             'spatialFrequency (cyc/deg), '
                             'temporalFrequency (Hz), '
                             'direction ([0, 2*pi)), '
                             'contrast ([0, 1]), '
                             'radius (deg), '
                             'phase ([0, 2*pi)'
                             'indicatorColor (for photodiode, from -1 to 1)]. '
                             'for gap frames, the 2ed to 8th elements should be np.nan.')
        stim.set_value('data_formatting', ['isDisplay', 'firstFrameInCycle', 'spatialFrequency', 'temporalFrequency',
                                           'direction', 'contrast', 'radius', 'phase', 'indicatorColor'])
        stim.set_source('corticalmapping.VisualStim.DriftingGratingCircle for stimulus; '
                        'corticalmapping.VisualStim.DisplaySequence for display')
        stim.set_value('background_color', log_dict['stimulation']['background'])
        stim.finalize()

    def _add_drifting_checker_board_stimulation(self, log_dict, display_order):

        stim_name = log_dict['stimulation']['stimName']

        if stim_name != 'KSstimAllDir':
            raise ValueError('stimulus should be drifting checker board all directions.')

        display_frames = log_dict['presentation']['displayFrames']
        time_stamps = log_dict['presentation']['timeStamp']

        display_frames = [list(f) for f in display_frames]

        for i in range(len(display_frames)):
            if display_frames[i][4] == 'B2U':
                display_frames[i][4] = 0
            elif display_frames[i][4] == 'U2B':
                display_frames[i][4] = 1
            elif display_frames[i][4] == 'L2R':
                display_frames[i][4] = 2
            elif display_frames[i][4] == 'R2L':
                display_frames[i][4] = 3

        frame_array = np.array(display_frames)
        frame_array[np.equal(frame_array, None)] = np.nan
        frame_array = frame_array.astype(np.float32)

        stim = self.create_timeseries('TimeSeries', ft.int2str(display_order, 2) + '_' + stim_name,
                                      'stimulus')
        stim.set_time(time_stamps)
        stim.set_data(frame_array, unit='', conversion=np.nan, resolution=np.nan)
        stim.set_comments('the timestamps of displayed frames (saved in data) are referenced to the start of'
                          'this particular display, not the master time clock. For more useful timestamps, check'
                          '/processing for aligned photodiode onset timestamps.')
        stim.set_description('data formatting: [isDisplay (0:gap; 1:display), '
                             'square polarity (1: not reversed; -1: reversed), '
                             'sweeps, ind, index in sweep table, '
                             'indicatorColor (for photodiode, from -1 to 1)]. '
                             'direction (B2U: 0, U2B: 1, L2R: 2, R2L: 3), '
                             'for gap frames, the 2ed to 3th elements should be np.nan.')
        stim.set_value('data_formatting', ['isDisplay', 'squarePolarity', 'sweepIndex', 'indicatorColor', 'sweepDirection'])
        stim.set_source('corticalmapping.VisualStim.KSstimAllDir for stimulus; '
                        'corticalmapping.VisualStim.DisplaySequence for display')
        stim.set_value('background_color', log_dict['stimulation']['background'])
        stim.finalize()

        display_info = hl.analysisMappingDisplayLog(display_log=log_dict)
        display_grp = self.file_pointer['processing'].create_group('mapping_display_info')
        display_grp.attrs['description'] = 'This group saves the useful infomation about the retiotopic mapping visual' \
                                           'stimulation (drifting checker board sweeps in all directions). Generated ' \
                                           'by the corticalmapping.HighLevel.analysisMappingDisplayLog() function.'
        for direction, value in display_info.items():
            dir_grp = display_grp.create_group(direction)
            dir_grp.attrs['description'] = 'group containing the relative information about all sweeps in a particular' \
                                           'sweep direction. B: bottom, U: up, L: nasal, R: temporal (for stimulus to' \
                                           'the right eye)'
            ind_dset = dir_grp.create_dataset('onset_index', data=value['ind'])
            ind_dset.attrs['description'] = 'indices of sweeps of current direction in the whole experiment'
            st_dset = dir_grp.create_dataset('start_time', data=value['startTime'])
            st_dset.attrs['description'] = 'sweep start time relative to stimulus onset (second)'
            sd_dset = dir_grp.create_dataset('sweep_duration', data=value['sweepDur'])
            sd_dset.attrs['description'] = 'sweep duration (second)'
            equ_dset = dir_grp.create_dataset('phase_retinotopy_equation', data=[value['slope'], value['intercept']])
            equ_dset.attrs['description'] = 'the linear equation to transform fft phase into retinotopy visual degrees.' \
                                            'degree = phase * slope + intercept'
            equ_dset.attrs['data_format'] = ['slope', 'intercept']

    def analyze_sparse_noise_frames(self):
        """
        analyze sparse noise display frames saved in '/stimulus/presentation', extract information about onset of
        each displayed square, and save into '/processing':

        data formatting is self explanatory inside the created group
        """

        stim_list = self.file_pointer['stimulus/presentation'].keys()
        sparse_noise_displays = []
        for stim in stim_list:
            if 'SparseNoise' in stim:
                sparse_noise_displays.append(stim)
        if len(sparse_noise_displays) == 0:
            print('No sparse noise display log found, abort.')
            return None

        for snd in sparse_noise_displays:
            frames = self.file_pointer['stimulus/presentation'][snd]['data'].value
            frames = [tuple(x) for x in frames]
            dtype = [('isDisplay', int), ('azimuth', float), ('altitude', float), ('sign', int), ('isOnset', int)]
            frames = np.array(frames, dtype=dtype)

            allSquares = []
            for i in range(len(frames)):
                if frames[i]['isDisplay'] == 1 and (i == 0 or
                                                    frames[i - 1]['azimuth'] != frames[i]['azimuth'] or
                                                    frames[i - 1]['altitude'] != frames[i]['altitude'] or
                                                    frames[i - 1]['sign'] != frames[i]['sign']):
                    allSquares.append(np.array((i, frames[i]['azimuth'], frames[i]['altitude'], frames[i]['sign']),
                                               dtype=np.float32))

            allSquares = np.array(allSquares)

            snd_group = self.file_pointer['processing'].create_group(snd+'_squares')
            squares_dset = snd_group.create_dataset('onset_frame_index', data = allSquares)
            snd_group.create_dataset('data_formatting', data =['display frame indices for the onset of each square',
                                                               'azimuth of each square',
                                                               'altitude of each square',
                                                               'sign of each square'])
            squares_dset.attrs['description'] = 'intermediate processing step of sparse noise display log. Containing ' \
                                                'the information about the onset of each displayed square.'

    def _check_display_order(self, display_order=None):
        """
        check display order make sure each presentation has a unique position, and move from increment order.
        also check the given display_order is of the next number
        """
        stimuli = self.file_pointer['stimulus/presentation'].keys()

        print('\nExisting visual stimuli:')
        print('\n'.join(stimuli))

        stimuli = [int(s[0:s.find('_')]) for s in stimuli]
        stimuli.sort()
        if stimuli != range(len(stimuli)):
            raise ValueError('display order is not incremental.')

        if display_order is not None:

            if display_order != len(stimuli):
                raise ValueError('input display order not the next display.')

    def add_visual_stimulations(self, log_paths):

        exist_stimuli = self.file_pointer['stimulus/presentation'].keys()

        for i, log_path in enumerate(log_paths):
            self.add_visual_stimulation(log_path, i + len(exist_stimuli))

    def add_photodiode_onsets(self, digitizeThr=0.9, filterSize=0.01, segmentThr=0.01, smallestInterval=0.03,
                              expected_onsets_number=None):
        """
        intermediate processing step for analysis of visual display. Containing the information about the onset of
        photodiode signal. Timestamps are extracted from photodiode signal, should be aligned to the master clock.
        extraction is done by corticalmapping.HighLevel.segmentMappingPhotodiodeSignal() function. The raw signal
        was first digitized by the digitize_threshold, then filtered by a gaussian fileter with filter_size. Then
        the derivative of the filtered signal was calculated by numpy.diff. The derivative signal was then timed
        with the digitized signal. Then the segmentation_threshold was used to detect rising edge of the resulting
        signal. Any onset with interval from its previous onset smaller than smallest_interval will be discarded.
        the resulting timestamps of photodiode onsets will be saved in 'processing/photodiode_onsets' timeseries

        :param digitizeThr: float
        :param filterSize: float
        :param segmentThr: float
        :param smallestInterval: float
        :param expected_onsets_number: int, expected number of photodiode onsets, may extract from visual display
                                       log. if extracted onset number does not match this number, the process will
                                       be abort. If None, no such check will be performed.
        :return:
        """
        fs = self.file_pointer['general/extracellular_ephys/sampling_rate'].value
        pd = self.file_pointer['acquisition/timeseries/photodiode/data'].value * \
             self.file_pointer['acquisition/timeseries/photodiode/data'].attrs['conversion']

        # plt.plot(pd)
        # plt.show()

        pd_onsets = hl.segmentMappingPhotodiodeSignal(pd, digitizeThr=digitizeThr, filterSize=filterSize,
                                                      segmentThr=segmentThr, Fs=fs, smallestInterval=smallestInterval)

        if expected_onsets_number is not None:
            if len(pd_onsets) != expected_onsets_number:
                raise ValueError('The number of photodiode onsets (' + str(len(pd_onsets)) + ') and the expected '
                                 'number of sweeps ' + str(expected_onsets_number) + ' do not match. Abort.')

        pd_ts = self.create_timeseries('TimeSeries', 'photodiode_onsets', modality='other')
        pd_ts.set_time(pd_onsets)
        pd_ts.set_data([], unit='', conversion=np.nan, resolution=np.nan)
        pd_ts.set_description('intermediate processing step for analysis of visual display. '
                              'Containing the information about the onset of photodiode signal. Timestamps '
                              'are extracted from photodiode signal, should be aligned to the master clock.'
                              'extraction is done by corticalmapping.HighLevel.segmentMappingPhotodiodeSignal()'
                              'function. The raw signal was first digitized by the digitize_threshold, then '
                              'filtered by a gaussian fileter with filter_size. Then the derivative of the filtered '
                              'signal was calculated by numpy.diff. The derivative signal was then timed with the '
                              'digitized signal. Then the segmentation_threshold was used to detect rising edge of '
                              'the resulting signal. Any onset with interval from its previous onset smaller than '
                              'smallest_interval will be discarded.')
        pd_ts.set_path('/processing/photodiode_onsets')
        pd_ts.set_value('digitize_threshold', digitizeThr)
        pd_ts.set_value('fileter_size', filterSize)
        pd_ts.set_value('segmentation_threshold', segmentThr)
        pd_ts.set_value('smallest_interval', smallestInterval)
        pd_ts.finalize()

    def plot_spike_waveforms(self, unitn, channel_names, fig=None, t_range=(-0.002, 0.002), **kwargs):
        """
        plot spike waveforms

        :param unitn: str, name of ephys unit, should be in '/processing/ephys_units/UnitTimes'
        :param channel_names: list of strs, channel names in continuous recordings, should be in '/acquisition/timeseries'
        :param fig: matplotlib figure object
        :param t_range: tuple of two floats, time range to plot along spike time stamps
        :param kwargs: inputs to matplotlib.axes.plot() function
        :return: fig
        """
        # print 'in nwb tools.'

        if unitn not in self.file_pointer['processing/ephys_units/UnitTimes'].keys():
            raise LookupError('Can not find ephys unit: ' + unitn + '.')

        for channeln in channel_names:
            if channeln not in self.file_pointer['acquisition/timeseries'].keys():
                raise LookupError('Can not find continuous recording: ' + channeln + '.')

        unit_ts = self.file_pointer['processing/ephys_units/UnitTimes'][unitn]['times'].value

        channels = []
        sample_rate = None
        starting_time = None
        channel_len = None

        for channeln in channel_names:

            if sample_rate is None:
                sample_rate = self.file_pointer['acquisition/timeseries'][channeln]['starting_time'].attrs['rate']
            else:
                if sample_rate != self.file_pointer['acquisition/timeseries'][channeln]['starting_time'].attrs['rate']:
                    raise ValueError('sample rate of channel ' + channeln + ' does not equal the sample rate of other '
                                                                            'channels.')

            if starting_time is None:
                starting_time = self.file_pointer['acquisition/timeseries'][channeln]['starting_time'].value
            else:
                if starting_time != self.file_pointer['acquisition/timeseries'][channeln]['starting_time'].value:
                    raise ValueError('starting time of channel ' + channeln + ' does not equal the start time of '
                                                                              'other channels.')


            curr_ch = self.file_pointer['acquisition/timeseries'][channeln]['data'].value
            curr_rate = self.file_pointer['acquisition/timeseries'][channeln]['starting_time'].attrs['rate']

            if channel_len is None:
                channel_len = len(curr_ch)
            else:
                if len(curr_ch) != channel_len:
                    raise ValueError('Length of channel ' + channeln + ' does not equal the lengths of other '
                                                                       'channels.')

            curr_conversion = self.file_pointer['acquisition/timeseries'][channeln]['data'].attrs['conversion']
            curr_ch = curr_ch.astype(np.float32) * curr_conversion
            curr_ch = ta.butter_bandpass(curr_ch, cutoffs=(300., 6000.), fs=curr_rate)
            channels.append(curr_ch)

        channel_ts = starting_time + np.arange(channel_len, dtype=np.float32) / sample_rate


        fig = pt.plot_spike_waveforms(unit_ts=unit_ts, channels=channels, channel_ts=channel_ts, fig=fig,
                                      t_range=t_range, channel_names=channel_names, **kwargs)
        fig.suptitle(unitn)

        return fig





    def add_segmentation_result(self):
        # todo: finish this method
        pass

    def add_roi_traces(self):
        # todo: finish this method
        pass

    def add_strf(self):
        # todo: finish this method
        pass

    def add_motion_correction(self):
        # not for now
        pass

    def add_sync_data(self):
        # not for now
        pass

    def add_kilosort_clusters(self, folder, module_name, ind_start=None, ind_end=None):
        """
        expects spike clusters.npy, spike_templates.npy, and spike_times.npy in the folder. use only for the direct outputs of kilosort,
        that haven't been modified with phy-template.
        :param folder:
        :return:
        """

        # if ind_start == None:
        #     ind_start = 0
        #
        # if ind_end == None:
        #     ind_end = self.file_pointer['acquisition/timeseries/photodiode/num_samples'].value
        #
        # if ind_start >= ind_end:
        #     raise ValueError('ind_end should be larger than ind_start.')
        #
        # spike_clusters = np.load(os.path.join(folder, 'spike_clusters.npy'))
        # spike_templates = np.load(os.path.join(folder, 'spike_templates.npy'))
        # spikes_times = np.load(os.path.join(folder, 'spike_times.npy'))
        # templates = np.load(os.path.join(folder, 'templates.npy'))

        # not for now
        pass



if __name__ == '__main__':

    # =========================================================================================================
    # tmp_path = r"E:\data\python_temp_folder\test.nwb"
    # open_ephys_folder = r"E:\data\2016-07-19-160719-M256896\100_spontaneous_2016-07-19_09-45-06_Jun"
    # rf = RecordedFile(tmp_path, identifier='', description='')
    # rf.add_open_ephys_data(open_ephys_folder, '100', ['wf_read', 'wf_trigger', 'visual_frame'])
    # rf.close()
    # =========================================================================================================

    # =========================================================================================================
    # tmp_path = r"E:\data\python_temp_folder\test.nwb"
    # rf = RecordedFile(tmp_path)
    # rf.add_general()
    # rf.close()
    # =========================================================================================================

    # =========================================================================================================
    # tmp_path = r"E:\data\python_temp_folder\test.nwb"
    # rf = RecordedFile(tmp_path)
    # rf.add_acquisition_image('surface_vas_map', np.zeros((10, 10)), description='surface vasculature map')
    # rf.close()
    # =========================================================================================================

    # =========================================================================================================
    # tmp_path = r"E:\data\python_temp_folder\test.nwb"
    # data_path = r"E:\data\2016-07-25-160722-M256896\processed_1"
    # rf = RecordedFile(tmp_path)
    # rf.add_phy_template_clusters(folder=data_path, module_name='LGN')
    # rf.close()
    # =========================================================================================================

    # =========================================================================================================
    # tmp_path = r"E:\data\python_temp_folder\test.nwb"
    # data_path = r"E:\data\2016-07-25-160722-M256896\processed_1"
    # rf = RecordedFile(tmp_path)
    # rf.add_kilosort_clusters(folder=data_path, module_name='LGN_kilosort')
    # rf.close()
    # =========================================================================================================

    # =========================================================================================================
    # tmp_path = r"E:\data\python_temp_folder\test.nwb"
    # log_path = r"E:\data\2016-06-29-160610-M240652-Ephys\101_160610172256-SparseNoise-M240652-Jun-0-" \
    #            r"notTriggered-complete.pkl"
    # rf = RecordedFile(tmp_path)
    # rf.add_visual_stimulation(log_path)
    # rf.close()
    # =========================================================================================================

    # =========================================================================================================
    # tmp_path = r"E:\data\python_temp_folder\test.nwb"
    # log_path = r"\\aibsdata2\nc-ophys\CorticalMapping\IntrinsicImageData\161017-M274376-FlashingCircle" \
    #            r"\161017162026-FlashingCircle-M274376-Sahar-101-Triggered-complete.pkl"
    # rf = RecordedFile(tmp_path)
    # rf.add_visual_stimulation(log_path, display_order=1)
    # rf.close()
    # =========================================================================================================

    # =========================================================================================================
    # tmp_path = r"E:\data\python_temp_folder\test.nwb"
    # log_paths = [r"\\aibsdata2\nc-ophys\CorticalMapping\IntrinsicImageData\161017-M274376-FlashingCircle\161017162026-FlashingCircle-M274376-Sahar-101-Triggered-complete.pkl",
    #              r"E:\data\2016-06-29-160610-M240652-Ephys\101_160610172256-SparseNoise-M240652-Jun-0-notTriggered-complete.pkl",]
    # rf = RecordedFile(tmp_path)
    # rf.add_visual_stimulations(log_paths)
    # rf.close()
    # =========================================================================================================

    # =========================================================================================================
    # tmp_path = r"E:\data\python_temp_folder\test.nwb"
    # log_paths = [r"C:\data\sequence_display_log\161018164347-UniformContrast-MTest-Jun-255-notTriggered-complete.pkl"]
    # rf = RecordedFile(tmp_path)
    # rf.add_visual_stimulations(log_paths)
    # rf.close()
    # =========================================================================================================

    # =========================================================================================================
    # tmp_path = r"E:\data\python_temp_folder\test.nwb"
    # # log_paths = [r"C:\data\sequence_display_log\160205131514-ObliqueKSstimAllDir-MTest-Jun-255-notTriggered-incomplete.pkl"]
    # log_paths = [r"C:\data\sequence_display_log\161018174812-DriftingGratingCircle-MTest-Jun-255-notTriggered-complete.pkl"]
    # rf = RecordedFile(tmp_path)
    # rf.add_visual_stimulations(log_paths)
    # rf.close()
    # =========================================================================================================

    # =========================================================================================================
    img_data_path = r"E:\data\python_temp_folder\img_data.hdf5"
    # img_data = h5py.File(img_data_path)
    # dset = img_data.create_dataset('data', data=np.random.rand(1000, 1000, 100))
    # dset.attrs['conversion'] = np.nan
    # dset.attrs['resolution'] = np.nan
    # dset.attrs['unit'] = ''
    # img_data.close()

    ts = np.random.rand(1000)

    tmp_path = r"E:\data\python_temp_folder\test.nwb"
    rf = RecordedFile(tmp_path)
    rf.add_acquired_image_series_as_remote_link('test_img', image_file_path=img_data_path, dataset_path='/data',
                                                timestamps=ts)
    rf.close()


    print('for debug ...')