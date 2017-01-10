__author__ = 'junz'

import os
import json
import numpy as np
import itertools
import scipy.stats as stats
import matplotlib.pyplot as plt
import core.ImageAnalysis as ia
import core.TimingAnalysis as ta
import tifffile as tf
import RetinotopicMapping as rm
import core.FileTools as ft
import scipy.ndimage as ni
from toolbox.misc import BinarySlicer

try:
    # from r_neuropil import NeuropilSubtract as NS
    from allensdk.brain_observatory.r_neuropil import NeuropilSubtract as NS
except Exception as e:
    print 'fail to import neural pil subtraction module ...'
    print e


def translateMovieByVasculature(mov, parameterPath, matchingDecimation=2, referenceDecimation=2, verbose=True):
    '''

    :param mov: movie before translation (could be 2d (just one frame) or 3d)
    :param parameterPath: path to the json file with translation parameters generated by VasculatureMapMatching GUI
    :param movDecimation: decimation factor from movie vasculature image to movie
    :param mappingDecimation: decimation factor from mapping vasculature image to mapped areas, usually 2
    :return: translated movie
    '''

    with open(parameterPath) as f:
        matchingParams = json.load(f)

    matchingDecimation = float(matchingDecimation); referenceDecimation=float(referenceDecimation)

    if matchingParams['Xoffset']%matchingDecimation != 0: print 'Original Xoffset is not divisble by movDecimation. Taking the floor integer.'
    if matchingParams['Yoffset']%matchingDecimation != 0: print 'Original Yoffset is not divisble by movDecimation. Taking the floor integer.'

    offset =  [int(matchingParams['Xoffset']/matchingDecimation),
               int(matchingParams['Yoffset']/matchingDecimation)]

    if matchingParams['ReferenceMapHeight']%matchingDecimation != 0: print 'Original ReferenceMapHeight is not divisble by movDecimation. Taking the floor integer.'
    if matchingParams['ReferenceMapWidth']%matchingDecimation != 0: print 'Original ReferenceMapWidth is not divisble by movDecimation. Taking the floor integer.'

    outputShape = [int(matchingParams['ReferenceMapHeight']/matchingDecimation),
                   int(matchingParams['ReferenceMapHeight']/matchingDecimation)]

    movT = ia.rigid_transform_cv2(mov, zoom=matchingParams['Zoom'], rotation=matchingParams['Rotation'], offset=offset, outputShape=outputShape)

    if matchingDecimation / referenceDecimation != 1:
        movT = ia.rigid_transform_cv2(movT, zoom=matchingDecimation / referenceDecimation)

    if verbose: print 'shape of output movie:', movT.shape

    return movT


def translateHugeMovieByVasculature(inputPath, outputPath, parameterPath, outputDtype=None, matchingDecimation=2,
                                    referenceDecimation=2,chunkLength=100,verbose=True):
    '''
    translate huge .npy matrix with alignment parameters into another huge .npy matrix without loading everything into memory
    :param inputPath: path of input movie (.npy file)
    :param outputPath: path of output movie (.npy file)
    :param outputDtype: data type of output movie
    :param parameterPath: path to the json file with translation parameters generated by VasculatureMapMatching GUI
    :param matchingDecimation: decimation factor on the matching side (usually 2)
    :param referenceDecimation: decimation factor on the reference side (if using standard retinotopic mapping pkl file, should be 2)
    :param chunkLength: frame number of chunks
    :return:
    '''

    chunkLength = int(chunkLength)

    inputMov = BinarySlicer(inputPath)

    if outputDtype is None: outputDtype = inputMov.dtype.str

    if len(inputMov.shape)!=3: raise ValueError, 'Input movie should be 3-d!'

    frameNum = inputMov.shape[0]

    if outputPath[-4:]!='.npy': outputPath += '.npy'

    if verbose: print '\nInput movie shape:', inputMov.shape


    chunkNum = frameNum // chunkLength
    if frameNum % chunkLength == 0:
        if verbose:
            print 'Translating in chunks: '+ str(chunkNum)+' x '+str(chunkLength)+' frame(s)'
    else:
        chunkNum += 1
        if verbose: print 'Translating in chunks: '+str(chunkNum-1)+' x '+str(chunkLength)+' frame(s)'+' + '+str(frameNum % chunkLength)+' frame(s)'

    frameT1 = translateMovieByVasculature(inputMov[0,:,:],parameterPath=parameterPath,matchingDecimation=matchingDecimation,referenceDecimation=referenceDecimation,verbose=False)
    plt.imshow(frameT1,cmap='gray')
    plt.show()

    if verbose: print 'Output movie shape:', (frameNum,frameT1.shape[0],frameT1.shape[1]), '\n'

    with open(outputPath, 'wb') as f:
        np.lib.format.write_array_header_1_0(f, {'descr':outputDtype, 'fortran_order':False, 'shape':(frameNum,frameT1.shape[0],frameT1.shape[1])})

        for i in range(chunkNum):
            indStart = i*chunkLength
            indEnd = (i+1)*chunkLength
            if indEnd > frameNum: indEnd = frameNum
            currMov = inputMov[indStart:indEnd,:,:]
            if verbose: print 'Translating frame '+str(indStart)+' to frame '+str(indEnd)+'.\t'+str(i*100./chunkNum)+'%'
            currMovT = translateMovieByVasculature(currMov,parameterPath=parameterPath,matchingDecimation=matchingDecimation,referenceDecimation=referenceDecimation,verbose=False)
            currMovT = currMovT.astype(outputDtype)
            currMovT.reshape((np.prod(currMovT.shape),)).tofile(f)


def segmentMappingPhotodiodeSignal(pd, digitizeThr=0.9, filterSize=0.01, segmentThr=0.02, Fs=10000.,
                                   smallestInterval=10., verbose=False):
    '''

    :param pd: photodiode from mapping jphys file
    :param digitizeThr: threshold to digitize photodiode readings
    :param filterSize: gaussian filter size to filter photodiode signal, sec
    :param segmentThr: threshold to detect the onset of each stimulus sweep
    :param Fs: sampling rate
    :return:
    '''

    pdDigitized = np.array(pd)

    pdDigitized[pd<digitizeThr] = 0.; pdDigitized[pd>=digitizeThr] = 5.

    filterDataPoint = int(filterSize*Fs)

    pdFiltered = ni.filters.gaussian_filter(pdDigitized, filterDataPoint)
    pdFilteredDiff = np.diff(pdFiltered)
    pdFilteredDiff = np.hstack(([0],pdFilteredDiff))
    pdSignal = np.multiply(pdDigitized, pdFilteredDiff)
    # plt.plot(pdSignal[:1000000])
    # plt.show()

    displayOnsets = ta.get_onset_timeStamps(pdSignal, Fs, threshold = segmentThr, onsetType='raising')

    trueDisplayOnsets=[]
    for i, displayOnset in enumerate(displayOnsets):
        if i == 0:
            trueDisplayOnsets.append(displayOnset)
            currOnset = displayOnset
        else:
            if displayOnset - currOnset > smallestInterval:
                trueDisplayOnsets.append(displayOnset)
                currOnset = displayOnset

    print '\nNumber of photodiode onsets:', len(trueDisplayOnsets)

    if verbose:
        print '\nDisplay onsets (sec):'
        print '\n'.join([str(o) for o in trueDisplayOnsets])

    print '\n'

    return np.array(trueDisplayOnsets)

'''
def getlogPathList(date,#string
                   mouseID,#string
                   stimulus='',#string
                   userID='',#string
                   fileNumber='',#string
                   displayFolder=r'\\W7DTMJ007LHW\data\sequence_display_log'):
    logPathList = []
    for f in os.listdir(displayFolder):
        fn, ext = os.path.splitext(f)
        strings = fn.split('-')
        try: dateTime,stim,mouse,user,fileNum=strings[0:5]
        except Exception as e:
            # print 'Can not read path:',f,'\n',e
            continue
        if (dateTime[0:6] == date) and (mouseID in mouse) and (stimulus in stim) and (userID in user) and (fileNumber == fileNum):
            logPathList.append(os.path.join(displayFolder,f))
    print '\n'+'\n'.join(logPathList)+'\n'
    return logPathList
'''

def findLogPath(date,#string
                mouseID,#string
                stimulus='',#string
                userID='',#string
                fileNumber='',#string
                displayFolder=r'\\W7DTMJ007LHW\data\sequence_display_log'):
    logPathList = []
    for f in os.listdir(displayFolder):
        fn, ext = os.path.splitext(f)
        strings = fn.split('-')
        try: dateTime,stim,mouse,user,fileNum,trigger,complete=strings
        except Exception as e:
            # print 'Can not read path:',f,'\n',e
            continue
        if (dateTime[0:6] == date) and (mouseID in mouse) and (stimulus in stim) and (userID in user) and (fileNumber == fileNum) and (ext == '.pkl'):
            logPathList.append(os.path.join(displayFolder,f))
    print '\n'+'\n'.join(logPathList)+'\n'
    if len(logPathList)==0: raise LookupError, 'Can not find visual display Log.'
    elif len(logPathList)>1: raise LookupError, 'Find more than one visual display Log!'
    return logPathList[0]


def getVasMap(vasMapPaths,
              dtype = np.dtype('<u2'),
              headerLength = 116,
              tailerLength = 218,
              column = 1024,
              row = 1024,
              frame = 1,
              crop = None,
              mergeMethod = np.mean, # np.median, np.min, np.max
              ):

    vasMaps = []
    for vasMapPath in vasMapPaths:
        currVasMap,_,_= ft.importRawJCamF(vasMapPath,saveFolder=None,dtype=dtype,headerLength=headerLength,tailerLength=tailerLength,
                                          column=column,row=row,frame=frame,crop=crop)
        vasMaps.append(currVasMap[0].astype(np.float32))
    vasMap = mergeMethod(vasMaps,axis=0)

    return vasMap

'''
def analysisMappingDisplayLogs(logPathList):
    ====================================================================================================================
    :param logFileList: list of paths of all visual display logs of a mapping experiment
    :return:
    B2U: dictionary of all bottom up sweeps
        'ind': indices of these sweeps in the whole experiments
        'startTime': starting time relative to stimulus onset
        'endTime': end time relative to stimulus onset
        'slope': slope of the linear relationship between phase and retinotopic location
        'intercept': intercept of the linear relationship between phase and retinotopic location

    same for U2B, L2R and R2L
    ====================================================================================================================

    displayInfo = {
                   'B2U':{'ind':[],'startTime':[],'sweepDur':[],'slope':[],'intercept':[]},
                   'U2B':{'ind':[],'startTime':[],'sweepDur':[],'slope':[],'intercept':[]},
                   'L2R':{'ind':[],'startTime':[],'sweepDur':[],'slope':[],'intercept':[]},
                   'R2L':{'ind':[],'startTime':[],'sweepDur':[],'slope':[],'intercept':[]}
                   }

    ind=0

    for logPath in sorted(logPathList):
        log = ft.loadFile(logPath)

        #get sweep direction
        direction = log['stimulation']['direction']
        if log['presentation']['displayOrder']==-1: direction=direction[::-1]
        currDict = displayInfo[direction]

        #get number of sweeps
        sweepNum = log['stimulation']['iteration'] * log['presentation']['displayIteration']
        currDict['ind'] += range(ind,ind+sweepNum)
        ind += sweepNum

        #get startTime, sweep duration, phase position relationship
        if not currDict['startTime']:
            refreshRate = float(log['monitor']['refreshRate'])
            interFrameInterval = np.mean(np.diff(log['presentation']['timeStamp']))
            if interFrameInterval > (1.01/refreshRate): raise ValueError, 'Mean visual display too long: '+str(interFrameInterval)+'sec' # check display
            if interFrameInterval < (0.99/refreshRate): raise ValueError, 'Mean visual display too short: '+str(interFrameInterval)+'sec' # check display

            if log['presentation']['displayOrder']==1: currDict['startTime'] = -1 * log['stimulation']['preGapFrame'] / refreshRate
            if log['presentation']['displayOrder']==-1: currDict['startTime'] = -1 * log['stimulation']['postGapFrame'] / refreshRate

            currDict['sweepDur'] = len(log['presentation']['displayFrames']) / (log['stimulation']['iteration'] * log['presentation']['displayIteration'] * refreshRate)

            currDict['slope'], currDict['intercept'] = rm.getPhasePositionEquation(log)

    return displayInfo
'''

def analysisMappingDisplayLog(display_log):
    '''
    :param logFile: log dictionary or the path of visual display log of a mapping experiment
    :return:
    displayInfo: dictionary, for each direction ('B2U','U2B','L2R','R2L'):
        'ind': indices of these sweeps in the whole experiment
        'startTime': starting time relative to stimulus onset
        'sweepDur': duration of the sweep
        'slope': slope of the linear relationship between phase and retinotopic location
        'intercept': intercept of the linear relationship between phase and retinotopic location

    same for U2B, L2R and R2L
    '''

    displayInfo = {
                   'B2U':{'ind':[],'startTime':[],'sweepDur':[],'slope':[],'intercept':[]},
                   'U2B':{'ind':[],'startTime':[],'sweepDur':[],'slope':[],'intercept':[]},
                   'L2R':{'ind':[],'startTime':[],'sweepDur':[],'slope':[],'intercept':[]},
                   'R2L':{'ind':[],'startTime':[],'sweepDur':[],'slope':[],'intercept':[]}
                   }

    if isinstance(display_log, dict):
        log = display_log
    elif isinstance(display_log, str):
        log = ft.loadFile(display_log)
    else:
        raise ValueError('log should be either dictionary or a path string!')

    #check display order
    if log['presentation']['displayOrder']==-1: raise ValueError, 'Display order is -1 (should be 1)!'
    refreshRate = float(log['monitor']['refreshRate'])

    #check display visual frame interval
    interFrameInterval = np.mean(np.diff(log['presentation']['timeStamp']))
    if interFrameInterval > (1.01/refreshRate): raise ValueError, 'Mean visual display too long: '+str(interFrameInterval)+'sec' # check display
    if interFrameInterval < (0.99/refreshRate): raise ValueError, 'Mean visual display too short: '+str(interFrameInterval)+'sec' # check display

    #get sweep start time relative to display onset
    try:
        startTime = -1 * log['stimulation']['preGapDur']
    except KeyError:
        startTime = -1 * log['stimulation']['preGapFrameNum'] / log['monitor']['refreshRate']
    print 'Movie chunk start time relative to sweep onset:',startTime,'sec'
    displayInfo['B2U']['startTime']=startTime;displayInfo['U2B']['startTime']=startTime
    displayInfo['L2R']['startTime']=startTime;displayInfo['R2L']['startTime']=startTime

    #get basic information
    frames = log['stimulation']['frames']
    displayIter = log['presentation']['displayIteration']
    sweepTable = log['stimulation']['sweepTable']
    dirList = []
    B2Uframes = []; U2Bframes = []; L2Rframes = []; R2Lframes = []

    # parcel frames for each direction
    for frame in frames:
        currDir = frame[4]
        if currDir not in dirList: dirList.append(currDir)
        if currDir=='B2U': B2Uframes.append(frame)
        elif currDir=='U2B': U2Bframes.append(frame)
        elif currDir=='L2R': L2Rframes.append(frame)
        elif currDir=='R2L': R2Lframes.append(frame)

    #get sweep order indices for each direction
    dirList = dirList * displayIter
    displayInfo['B2U']['ind'] = [ind for ind, dir in enumerate(dirList) if dir=='B2U']
    print 'B2U sweep order indices:',displayInfo['B2U']['ind']
    displayInfo['U2B']['ind'] = [ind for ind, dir in enumerate(dirList) if dir=='U2B']
    print 'U2B sweep order indices:',displayInfo['U2B']['ind']
    displayInfo['L2R']['ind'] = [ind for ind, dir in enumerate(dirList) if dir=='L2R']
    print 'L2R sweep order indices:',displayInfo['L2R']['ind']
    displayInfo['R2L']['ind'] = [ind for ind, dir in enumerate(dirList) if dir=='R2L']
    print 'R2L sweep order indices:',displayInfo['R2L']['ind']

    #get sweep duration for each direction
    displayInfo['B2U']['sweepDur'] = len(B2Uframes) / refreshRate
    print 'Chunk duration for B2U sweeps:', displayInfo['B2U']['sweepDur'], 'sec'
    displayInfo['U2B']['sweepDur'] = len(U2Bframes) / refreshRate
    print 'Chunk duration for U2B sweeps:', displayInfo['U2B']['sweepDur'], 'sec'
    displayInfo['L2R']['sweepDur'] = len(L2Rframes) / refreshRate
    print 'Chunk duration for L2R sweeps:', displayInfo['L2R']['sweepDur'], 'sec'
    displayInfo['R2L']['sweepDur'] = len(R2Lframes) / refreshRate
    print 'Chunk duration for R2L sweeps:', displayInfo['R2L']['sweepDur'], 'sec'

    #get phase position slopes and intercepts for each direction
    displayInfo['B2U']['slope'],displayInfo['B2U']['intercept'] = rm.getPhasePositionEquation2(B2Uframes,sweepTable)
    displayInfo['U2B']['slope'],displayInfo['U2B']['intercept'] = rm.getPhasePositionEquation2(U2Bframes,sweepTable)
    displayInfo['L2R']['slope'],displayInfo['L2R']['intercept'] = rm.getPhasePositionEquation2(L2Rframes,sweepTable)
    displayInfo['R2L']['slope'],displayInfo['R2L']['intercept'] = rm.getPhasePositionEquation2(R2Lframes,sweepTable)

    return displayInfo


def analyzeSparseNoiseDisplayLog(logPath):
    '''
    return the indices of visual display frames for each square in a sparse noise display

    return:
    allOnsetInd: the indices of frames for each square, list
    onsetIndWithLocationSign: indices of squares for each location and sign,
                              list with element structure [np.array([alt, azi]),sign,[list of indices of square onset]]
    '''

    log = ft.loadFile(logPath)

    if log['stimulation']['stimName'] != 'SparseNoise':
        raise LookupError('The stimulus type should be sparse noise!')


    frames = log['presentation']['displayFrames']
    frames = [tuple([np.array([x[1][1],x[1][0]]),x[2],x[3],i]) for i, x in enumerate(frames)]
    dtype = [('location',np.ndarray),('sign',int),('isOnset',int),('index',int)]
    frames = np.array(frames, dtype = dtype)

    allOnsetInd = []
    for i in range(len(frames)):
        if frames[i]['isOnset'] == 1 and (i == 0 or frames[i-1]['isOnset'] == -1):
            allOnsetInd.append(i)

    onsetFrames = frames[allOnsetInd]

    allSquares = list(set([tuple([x[0][0],x[0][1],x[1]]) for x in onsetFrames]))

    onsetIndWithLocationSign = []

    for square in allSquares:
        indices = []
        for j, onsetFrame in enumerate(onsetFrames):
            if onsetFrame['location'][0]==square[0] and onsetFrame['location'][1]==square[1] and onsetFrame['sign']==square[2]:
                indices.append(j)

        onsetIndWithLocationSign.append([np.array([square[0],square[1]]),square[2],indices])

    return allOnsetInd, onsetIndWithLocationSign


def getAverageDfMovie(movPath, frameTS, onsetTimes, chunkDur, startTime=0., temporalDownSampleRate=1,
                      is_load_all=False):
    '''
    :param movPath: path to the image movie
    :param frameTS: the timestamps for each frame of the raw movie
    :param onsetTimes: time stamps of onset of each sweep
    :param startTime: chunck start time relative to the sweep onset time (length of pre gray period)
    :param chunkDur: duration of each chunk
    :param temporalDownSampleRate: decimation factor in time after recording
    :return: averageed movie of all chunks
    '''

    if temporalDownSampleRate == 1:
        frameTS_real = frameTS
    elif temporalDownSampleRate >1:
        frameTS_real = frameTS[::temporalDownSampleRate]
    else:
        raise ValueError, 'temporal downsampling rate can not be less than 1!'

    if is_load_all:
        if movPath[-4:] == '.npy':
            try:
                mov = np.load(movPath)
            except ValueError:
                print 'Cannot load the entire npy file into memroy. Trying BinarySlicer...'
                mov = BinarySlicer(movPath)
        elif movPath[-4:] == '.tif':
            mov = tf.imread(movPath)
        else:
            mov, _, _ = ft.importRawJCamF(movPath)
    else:
        mov = BinarySlicer(movPath)

    aveMov = ia.get_average_movie(mov, frameTS_real, onsetTimes + startTime, chunkDur)

    meanFrameDur = np.mean(np.diff(frameTS_real))
    baselineFrameDur = int(abs(startTime) / meanFrameDur)

    baselinePicture = np.mean((aveMov[0:baselineFrameDur,:,:]).astype(np.float32),axis=0)
    _, aveMovNor, _ = ia.normalize_movie(aveMov, baselinePicture)

    return aveMov, aveMovNor


def getAverageDfMovieFromH5Dataset(dset, frameTS, onsetTimes, chunkDur, startTime=0., temporalDownSampleRate=1):
    '''
    :param dset: hdf5 dataset object, 3-d matrix, zyx
    :param frameTS: the timestamps for each frame of the raw movie
    :param onsetTimes: time stamps of onset of each sweep
    :param startTime: chunck start time relative to the sweep onset time (length of pre gray period)
    :param chunkDur: duration of each chunk
    :param temporalDownSampleRate: decimation factor in time after recording
    :return: aveMov:  3d array, zyx, float32, averageed movie of all chunks
             n: int, number of chunks averaged
             baseLinePicture: 2d array, float32, baseline picture, None if startTime < 0.
             ts: 1d array, float32, timestamps relative to onsets of the averge movie
    '''

    if temporalDownSampleRate == 1:
        frameTS_real = frameTS
    elif temporalDownSampleRate >1:
        frameTS_real = frameTS[::temporalDownSampleRate]
    else:
        raise ValueError, 'temporal downsampling rate can not be less than 1!'

    aveMov, n = ia.get_average_movie(dset, frameTS_real, onsetTimes + startTime, chunkDur, isReturnN=True)

    meanFrameDur = np.mean(np.diff(frameTS_real))
    ts = startTime + np.arange(aveMov.shape[0]) * meanFrameDur

    if startTime < 0.:
        baselineFrameDur = int(abs(startTime) / meanFrameDur)
        baselinePicture = np.mean((aveMov[0:baselineFrameDur,:,:]).astype(np.float32),axis=0)
    else:
        baselinePicture = None

    return aveMov.astype(np.float32), n, baselinePicture.astype(np.float32), ts.astype(np.float32)


def getMappingMovies(movPath,frameTS,displayOnsets,displayInfo,temporalDownSampleRate=1,saveFolder=None,savePrefix='',
                     FFTmode='peak',cycles=1,isRectify=False,is_load_all=False):
    '''

    :param movPath: path of total movie with all directions
    :param frameTS: time stamps of imaging frame
    :param displayOnsets: onset timing of selected chunk
    :param displayInfo: display information generated by the 'analysisMappingDisplayLog'
    :param temporalDownSampleRate: temporal down sample rate during decimation
    :param saveFolder: folder path to save averaged movies
    :param savePrefix: prefix of file name
    :param FFTmode: FFT detect peak or valley, takes 'peak' or 'valley'
    :param cycles: how many cycles in each chunk
    :param isRectify: if True, the fft will be done on the rectified normalized movie, anything below zero will be assigned as zero
    :param is_load_all: load the whole movie into memory or not
    :return: altPosMap,aziPosMap,altPowerMap,aziPowerMap
    '''
    maps = {}

    if FFTmode=='peak': isReverse=False
    elif FFTmode=='valley': isReverse=True
    else: raise LookupError, 'FFTmode should be either "peak" or "valley"!'

    for dir in ['B2U','U2B','L2R','R2L']:
        print '\nAnalyzing sweeps with direction:', dir

        onsetInd = list(displayInfo[dir]['ind'])

        for ind in displayInfo[dir]['ind']:
            if ind >= len(displayOnsets):
                print 'Visual Stimulation Direction:'+dir+' index:'+str(ind)+' was not displayed. Remove from averageing.'
                onsetInd.remove(ind)

        aveMov, aveMovNor = getAverageDfMovie(movPath=movPath,
                                              frameTS=frameTS,
                                              onsetTimes=displayOnsets[onsetInd],
                                              chunkDur=displayInfo[dir]['sweepDur'],
                                              startTime=displayInfo[dir]['startTime'],
                                              temporalDownSampleRate=temporalDownSampleRate,
                                              is_load_all=is_load_all)

        if isRectify:
            aveMovNorRec = np.array(aveMovNor)
            aveMovNorRec[aveMovNorRec < 0.] = 0.
            phaseMap, powerMap = rm.generatePhaseMap2(aveMovNorRec,cycles,isReverse)
        else:
            phaseMap, powerMap = rm.generatePhaseMap2(aveMov,cycles,isReverse)


        powerMap = powerMap / np.amax(powerMap)
        positionMap = phaseMap * displayInfo[dir]['slope'] + displayInfo[dir]['intercept']
        maps.update({'posMap_'+dir:positionMap,
                     'powerMap_'+dir:powerMap})

        if saveFolder is not None:
            if savePrefix:
                tf.imsave(os.path.join(saveFolder,savePrefix+'_aveMov_'+dir+'.tif'),aveMov.astype(np.float32))
                tf.imsave(os.path.join(saveFolder,savePrefix+'_aveMovNor_'+dir+'.tif'),aveMovNor.astype(np.float32))
            else:
                tf.imsave(os.path.join(saveFolder,savePrefix+'aveMov_'+dir+'.tif'),aveMov.astype(np.float32))
                tf.imsave(os.path.join(saveFolder,savePrefix+'aveMovNor_'+dir+'.tif'),aveMovNor.astype(np.float32))

    altPosMap = np.mean([maps['posMap_B2U'],maps['posMap_U2B']],axis=0)
    aziPosMap = np.mean([maps['posMap_L2R'],maps['posMap_R2L']],axis=0)

    altPowerMap = np.mean([maps['powerMap_B2U'],maps['powerMap_U2B']],axis=0)
    altPowerMap = altPowerMap / np.amax(altPowerMap)

    aziPowerMap = np.mean([maps['powerMap_L2R'],maps['powerMap_L2R']],axis=0)
    aziPowerMap = aziPowerMap / np.amax(aziPowerMap)

    return altPosMap,aziPosMap,altPowerMap,aziPowerMap


def regression_detrend(mov, roi, verbose=True):
    """
    detrend a movie by subtracting global trend as average activity in side the roi. It work on a pixel by pixel bases
    and use linear regress to determine the contribution of the global signal to the pixel activity.

    ref:
    1. J Neurosci. 2016 Jan 27;36(4):1261-72. doi: 10.1523/JNEUROSCI.2744-15.2016. Resolution of High-Frequency
    Mesoscale Intracortical Maps Using the Genetically Encoded Glutamate Sensor iGluSnFR. Xie Y, Chan AW, McGirr A,
    Xue S, Xiao D, Zeng H, Murphy TH.
    2. Neuroimage. 1998 Oct;8(3):302-6. The inferential impact of global signal covariates in functional neuroimaging
    analyses. Aguirre GK1, Zarahn E, D'Esposito M.

    :param mov: input movie
    :param roi: binary, weight and binaryNan roi to define global signal
    :return: detrended movie, trend, amp_map, rvalue_map
    """

    if len(mov.shape) != 3:
        raise(ValueError, 'Input movie should be 3-dimensional!')

    roi = ia.WeightedROI(roi)
    trend = roi.get_weighted_trace(mov)

    mov_new = np.empty(mov.shape, dtype=np.float32)
    slopes = np.empty((mov.shape[1], mov.shape[2]), dtype=np.float32)
    rvalues = np.empty((mov.shape[1], mov.shape[2]), dtype=np.float32)

    pixel_num = mov.shape[1] * mov.shape[2]

    n = 0

    for i, j in itertools.product(range(mov.shape[1]), range(mov.shape[2])):
        pixel_trace = mov[:, i, j]
        slope, intercept, r_value, p_value, stderr = stats.linregress(trend, pixel_trace)
        slopes[i, j] = slope
        rvalues[i, j] = r_value
        mov_new[:, i, j] = pixel_trace - trend * slope

        if verbose:
            if n % (pixel_num // 10) == 0:
                print 'progress:', int(round(float(n) * 100 / pixel_num)), '%'
        n += 1

    return mov_new, trend, slopes, rvalues


def neural_pil_subtraction(trace_center, trace_surround, lam=0.05):
    """
    use allensdk neural pil subtraction

    :param trace_center: input center trace
    :param trace_surround: input surround trace
    :param lam:
    :return:
        r: contribution of the surround to the center
        error: final cross-validation error
        trace: trace after neuropil subtracction
    """


    if trace_center.shape != trace_surround.shape:
        raise ValueError('center trace and surround trace should have same shape')

    if len(trace_center.shape) != 1:
        raise ValueError('input traces should be 1 dimensional!')

    trace_center = trace_center.astype(np.float)
    trace_surround = trace_surround.astype(np.float)

    ns = NS(lam=lam)

    # ''' normalize to have F_N in (0,1)'''
    # F_M = (trace_center - float(np.amin(trace_surround))) / float(np.amax(trace_surround) - np.amin(trace_surround))
    # F_N = (trace_surround - float(np.amin(trace_surround))) / float(np.amax(trace_surround) - np.amin(trace_surround))

    '''fitting model'''
    # ns.set_F(F_M, F_N)
    ns.set_F(trace_center, trace_surround)

    '''stop gradient descent at first increase of cross-validation error'''
    ns.fit()
    # ns.fit_block_coordinate_desc()

    return ns.r, ns.error, trace_center - ns.r * trace_surround


def get_lfp(trace, fs=30000., notch_base=60., notch_bandwidth=1., notch_harmonics=4, notch_order=2,
            lowpass_cutoff=300., lowpass_order=5):
    """

    :param trace: 1-d array, input trace
    :param fs: float, sampling rate, Hz
    :param notch_base: float, Hz, base frequency of powerline contaminating signal
    :param notch_bandwidth: float, Hz, filter bandwidth at each side of center frequency
    :param notch_harmonics: int, number of harmonics to filter out
    :param notch_order: int, order of butterworth bandpass notch filter, for a narrow band, shouldn't be larger than 2
    :param lowpass_cutoff: float, Hz, cutoff frequency of lowpass filter
    :param lowpass_order: int, order of butterworth lowpass filter
    :return: filtered LFP, 1-d array with same dtype as input trace
    """

    trace_float=trace.astype(np.float32)
    trace_notch = ta.notch_filter(trace_float, fs=fs, freq_base=notch_base, bandwidth=notch_bandwidth,
                                  harmonics=notch_harmonics, order=notch_order)
    lfp = ta.butter_lowpass(trace_notch, fs=fs, cutoff=lowpass_cutoff, order=lowpass_order)

    return lfp.astype(trace.dtype)


if __name__ == '__main__':

    #===========================================================================
    dateRecorded = '150930'
    mouseID = '187474'
    fileNum = 101
    displayFolder = r'\\W7DTMJ007LHW\data\sequence_display_log'
    logPath = findLogPath(date=dateRecorded,mouseID=mouseID,stimulus='KSstimAllDir',userID='',fileNumber=str(fileNum),displayFolder=displayFolder)
    displayInfo = analysisMappingDisplayLog(logPath)
    #===========================================================================

    #===========================================================================
    # inputPath = r"E:\data\python_temp_folder\testNPY.npy"
    # outputPath = r"E:\data\python_temp_folder\testNPY_T.npy"
    # parameterPath = r"E:\data\python_temp_folder\ExampleTraslationParameters.json"
    # inputMov = np.array([[range(100)]*100]*100,dtype=np.uint16)
    # tf.imshow(inputMov,vmin=0,vmax=100)
    # plt.show()
    # np.save(inputPath,inputMov)
    # translateHugeMovieByVasculature(inputPath,outputPath,parameterPath,matchingDecimation=1,referenceDecimation=1,chunkLength=3,verbose=True)
    # outputMov = np.load(outputPath)
    # tf.imshow(outputMov,vmin=0,vmax=100)
    # plt.show()
    #===========================================================================

    #===========================================================================
    # movPath = r"\\watersraid\data\Jun\150901-M177931\150901JCamF105_1_1_10.npy"
    # jphysPath = r"\\watersraid\data\Jun\150901-M177931\150901JPhys105"
    # vasMapPaths = [r"\\watersraid\data\Jun\150901-M177931\150901JCamF104"]
    # displayFolder = r'\\W7DTMJ007LHW\data\sequence_display_log'
    # saveFolder = r'E:\data\2015-09-04-150901-M177931-FlashCameraMapping'
    #
    # dateRecorded = '150901'
    # mouseID = '177931'
    # fileNum = '105'
    #
    # temporalDownSampleRate = 10
    #
    # # vasculature map parameters
    # vasMapDtype = np.dtype('<u2')
    # vasMapHeaderLength = 116
    # vasMapTailerLength = 218
    # vasMapColumn = 1024
    # vasMapRow = 1024
    # vasMapFrame = 1
    # vasMapCrop = None
    # vasMapMergeMethod = np.mean #np.median,np.min,np.max
    #
    # #jphys parameters
    # jphysDtype = np.dtype('>f')
    # jphysHeaderLength = 96 # length of the header for each channel
    # jphysChannels = ('photodiode2','read','trigger','photodiode','sweep','visualFrame','runningRef','runningSig','reward','licking')# name of all channels
    # jphysFs = 10000.
    #
    # #photodiode signal parameters
    # pdDigitizeThr=0.9
    # pdFilterSize=0.01
    # pdSegmentThr=0.02
    #
    # #image read signal parameters
    # readThreshold = 3.
    # readOnsetType='raising'
    #
    # #pos map and power map parameters
    # FFTmode='peak'
    # cycles=1
    #
    # #wrap experiment parameters
    # trialNum='4_5'
    # mouseType='Emx1-IRES-Cre;Camk2a-tTA;Ai93(TITL-GCaMP6f)'
    # isAnesthetized=False
    # visualStimType='KSstim'
    # visualStimBackground='gray'
    # analysisParams ={'phaseMapFilterSigma': 1.,
    #                  'signMapFilterSigma': 9.,
    #                  'signMapThr': 0.3,
    #                  'eccMapFilterSigma': 15.0,
    #                  'splitLocalMinCutStep': 10.,
    #                  'closeIter': 3,
    #                  'openIter': 3,
    #                  'dilationIter': 15,
    #                  'borderWidth': 1,
    #                  'smallPatchThr': 100,
    #                  'visualSpacePixelSize': 0.5,
    #                  'visualSpaceCloseIter': 15,
    #                  'splitOverlapThr': 1.1,
    #                  'mergeOverlapThr': 0.1}
    #
    #
    #
    #
    # vasMap = getVasMap(vasMapPaths,
    #                    dtype = vasMapDtype,
    #                    headerLength = vasMapHeaderLength,
    #                    tailerLength = vasMapTailerLength,
    #                    column = vasMapColumn,
    #                    row = vasMapRow,
    #                    frame = vasMapFrame,
    #                    crop = vasMapCrop,
    #                    mergeMethod = vasMapMergeMethod, # np.median, np.min, np.max
    #                    )
    #
    # tf.imsave(os.path.join(saveFolder,dateRecorded+'_M'+mouseID+'_vasMap.tif'),vasMap)
    #
    # _, jphys = ft.importRawNewJPhys(jphysPath,
    #                                 dtype = jphysDtype,
    #                                 headerLength = jphysHeaderLength,
    #                                 channels = jphysChannels,
    #                                 sf = jphysFs)
    #
    # pd = jphys['photodiode']
    #
    # displayOnsets = segmentMappingPhotodiodeSignal(pd,
    #                                                digitizeThr=pdDigitizeThr,
    #                                                filterSize=pdFilterSize,
    #                                                segmentThr=pdSegmentThr,
    #                                                Fs=jphysFs)
    #
    # imgFrameTS = ta.get_onset_timeStamps(jphys['read'],
    #                                    Fs=jphysFs,
    #                                    threshold=readThreshold,
    #                                    onsetType=readOnsetType)
    #
    # logPathList = getlogPathList(date=dateRecorded,
    #                              mouseID=mouseID,
    #                              stimulus='',#string
    #                              userID='',#string
    #                              fileNumber=fileNum,
    #                              displayFolder=displayFolder)
    #
    # displayInfo = analysisMappingDisplayLogs(logPathList)
    #
    # movies, moviesNor = getMappingMovies(movPath=movPath,
    #                                      frameTS=imgFrameTS,
    #                                      displayOnsets=displayOnsets,
    #                                      displayInfo=displayInfo,
    #                                      temporalDownSampleRate=temporalDownSampleRate)
    #
    # for dir,mov in movies.iteritems():
    #     tf.imsave(os.path.join(saveFolder,dateRecorded+'_M'+mouseID+'_aveMov_'+dir+'.tif'),mov)
    # for dir,movNor in moviesNor.iteritems():
    #     tf.imsave(os.path.join(saveFolder,dateRecorded+'_M'+mouseID+'_aveMovNor_'+dir+'.tif'),movNor)
    #
    # del moviesNor
    #
    # altPosMap,aziPosMap,altPowerMap,aziPowerMap = getPositionAndPowerMap(movies=movies,displayInfo=displayInfo,FFTmode=FFTmode,cycles=cycles)
    #
    # del movies
    #
    # f = plt.figure(figsize=(12,10))
    # f.suptitle(dateRecorded+'_M'+mouseID+'_Trial:'+trialNum)
    # ax1 = f.add_subplot(221); fig1 = ax1.imshow(altPosMap, vmin=-30,vmax=50,cmap='hsv',interpolation='nearest')
    # f.colorbar(fig1); ax1.set_title('alt position map')
    # ax2 = f.add_subplot(222); fig2 = ax2.imshow(altPowerMap, vmin=0,vmax=1,cmap='hot',interpolation='nearest')
    # f.colorbar(fig2); ax2.set_title('alt power map')
    # ax3 = f.add_subplot(223); fig3 = ax3.imshow(aziPosMap, vmin=0,vmax=120,cmap='hsv',interpolation='nearest')
    # f.colorbar(fig3); ax3.set_title('azi position map')
    # ax4 = f.add_subplot(224); fig4 = ax4.imshow(aziPowerMap, vmin=0,vmax=1,cmap='hot',interpolation='nearest')
    # f.colorbar(fig4); ax4.set_title('alt power map')
    #
    # f.savefig(os.path.join(saveFolder,dateRecorded+'_M'+mouseID+'_RetinotopicMappingTrial_'+trialNum+'.png'),dpi=300)
    #
    # trialObj = rm.RetinotopicMappingTrial(mouseID=mouseID,
    #                                       dateRecorded=int(dateRecorded),
    #                                       trialNum=trialNum,
    #                                       mouseType=mouseType,
    #                                       visualStimType=visualStimType,
    #                                       visualStimBackground=visualStimBackground,
    #                                       imageExposureTime=np.mean(np.diff(imgFrameTS)),
    #                                       altPosMap=altPosMap,
    #                                       aziPosMap=aziPosMap,
    #                                       altPowerMap=altPowerMap,
    #                                       aziPowerMap=altPowerMap,
    #                                       vasculatureMap=vasMap,
    #                                       isAnesthetized=isAnesthetized,
    #                                       params=analysisParams
    #                                       )
    #
    # trialDict = trialObj.generateTrialDict()
    # ft.saveFile(os.path.join(saveFolder,trialObj.getName()+'.pkl'),trialDict)
    #===========================================================================

    print 'for debug...'

