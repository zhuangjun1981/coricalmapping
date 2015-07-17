__author__ = 'junz'


import h5py
import numpy as np
import matplotlib.pyplot as plt
import core.PlottingTools as pt
import core.ImageAnalysis as ia
import core.FileTools as ft
import scipy.ndimage as ni
import itertools

def load_ROI_FromH5(h5Group):
    '''
    load ROI (either ROI or WeightedROI) object from a hdf5 data group
    '''

    dimension = h5Group.attrs['dimension']
    pixelSize = h5Group.attrs['pixelSize']
    if pixelSize == 'None': pixelSize = None
    pixelSizeUnit = h5Group.attrs['pixelSizeUnit']
    if pixelSizeUnit == 'None': pixelSizeUnit = None
    pixels = h5Group['pixels'].value

    if 'weights' in h5Group.keys():
        weights = h5Group['weights'].value
        mask = np.zeros(dimension,dtype=np.float32); mask[tuple(pixels)]=weights
        return WeightedROI(mask,pixelSize=pixelSize,pixelSizeUnit=pixelSizeUnit)
    else:
        mask = np.zeros(dimension,dtype=np.uint8); mask[tuple(pixels)]=1
        return ROI(mask,pixelSize=pixelSize,pixelSizeUnit=pixelSizeUnit)


def load_STRF_FromH5(h5Group):
    '''
    load SpatialTemporalReceptiveField object from a hdf5 data group
    '''

    time = h5Group.attrs['time']
    name = h5Group.parent.name[1:]+'.'+h5Group.parent.attrs['name']
    locations = []
    signs = []
    traces = []
    for key, traceItem in h5Group.iteritems():
        locations.append(np.array([traceItem.attrs['altitude'],traceItem.attrs['azimuth']]))
        signs.append((traceItem.attrs['sign']))
        traces.append(list(traceItem.value))

    return SpatialTemporalReceptiveField(locations,signs,traces,time,name)


def getSparseNoiseOnsetIndex(sparseNoiseDisplayLog):
    '''
    return the indices of visual display frames for each square in a sparse noise display

    return:
    allOnsetInd: the indices of frames for each square, list
    onsetIndWithLocationSign: indices of frames for each white square, list with element structure [np.array([alt, azi]),sign,[list of indices]]
    '''

    framesSingleIter = sparseNoiseDisplayLog['stimulation']['frames']

    frames = framesSingleIter * sparseNoiseDisplayLog['presentation']['displayIteration']
    frames = [tuple([np.array([x[1][0],x[1][1]]),x[2],x[3],i]) for i, x in enumerate(frames)]
    dtype = [('location',np.ndarray),('sign',int),('isOnset',int),('index',int)]
    frames = np.array(frames, dtype = dtype)

    allOnsetInd = np.where(frames['isOnset']==1)[0]

    onsetFrames = frames[allOnsetInd]

    allSquares = list(set([tuple([x[0][0],x[0][1],x[1]]) for x in onsetFrames]))

    onsetIndWithLocationSign = []

    for square in allSquares:
        indices = []
        for onsetFrame in onsetFrames:
            if onsetFrame['location'][0]==square[0] and onsetFrame['location'][1]==square[1] and onsetFrame['sign']==square[2]:
                indices.append(onsetFrame['index'])

        onsetIndWithLocationSign.append([np.array([square[0],square[1]]),square[2],indices])

    return allOnsetInd, onsetIndWithLocationSign


def getPeakWeightedROI(arr, thr):
    '''
    return: a WeightROI object representing the mask which contains the peak of arr and cut by the threshold (thr)
    '''
    if thr<=0: raise ValueError, 'Threshold too low!'
    nanLabel = np.isnan(arr)
    arr2=arr.copy();arr2[nanLabel]=0
    labeled,_=ni.label(arr2>=thr)
    peakCoor = np.array(np.where(arr2==np.amax(arr2))).transpose()[0]
    peakMask = ia.getMarkedMask(labeled,peakCoor)
    if peakMask is None: raise LookupError, 'Threshold too high!'
    else: return WeightedROI(arr2*peakMask)


def plot2DReceptiveField(mapArray,altPos,aziPos,plotAxis=None,**kwargs):
    '''
    plot a 2-d receptive field in a given axis

    :param mapArray: 2-d array, should be in the same coordinate system as meshgrid(altPos, aziPos)
    :param altPos: 1-d array, list of sample altitude positions, sorted from high to low
    :param aziPos: 1-d array, list of sample azimuth position, sorted from low to high
    :param plotAxis:
    :param kwargs: input to matplotlib.pyplot.imshow() function
    :return: plotAxis
    '''

    if plotAxis == None: f=plt.figure(figsize=(10,10)); plotAxis=f.add_subplot(111)
    plotAxis.imshow(mapArray,**kwargs)
    plotAxis.set_yticks(np.arange(len(altPos)))
    plotAxis.set_xticks(np.arange(len(aziPos)))
    plotAxis.set_yticklabels(altPos.astype(np.int))
    plotAxis.set_xticklabels(aziPos.astype(np.int))
    return plotAxis







class ROI(object):
    '''
    class of binary ROI
    '''

    def __init__(self, mask, pixelSize = None, pixelSizeUnit = None):
        '''
        :param mask: 2-d array, if not binary, non-zero and non-nan pixel will be included in mask,
                     zero-pixel will be considered as background
        :param pixelSize: float, can be None, one value (square pixel) or (width, height) for non-square pixel
        :param pixelSizeUnit: str, the unit of pixel size
        '''

        if len(mask.shape)!=2: raise ValueError, 'Input mask should be 2d.'

        self.dimension = mask.shape
        self.pixels = np.where(np.logical_and(mask!=0, ~np.isnan(mask)))

        self.pixelSize = pixelSize
        if pixelSize is None: self.pixelSizeUnit=None
        else: self.pixelSizeUnit = pixelSizeUnit


    def getBinaryMask(self):
        '''
        generate binary mask of the ROI, return 2d array, with 0s and 1s, dtype np.uint8
        '''
        mask = np.zeros(self.dimension,dtype=np.uint8)
        mask[self.pixels] = 1
        return mask


    def getNanMask(self):
        '''
        generate float mask of the ROI, return 2d array, with nans and 1s, dtype np.float32
        '''
        mask = np.zeros(self.dimension,dtype=np.float32)
        mask[:] = np.nan
        mask[self.pixels] = 1
        return mask


    def getPixelArea(self):
        '''
        return the area coverage of the ROI
        '''
        return len(self.pixels[0])


    def getCenter(self):
        '''
        return the center coordinates of the centroid of the mask
        '''
        return np.mean(np.array(self.pixels,dtype=np.float).transpose(),axis=0)


    def getTrace(self,mov):
        '''
        return trace of this ROI in a given movie
        '''
        binaryMask = self.getBinaryMask()
        trace = np.multiply(mov,np.array([binaryMask])).sum(axis=1).sum(axis=1)
        return trace


    def plotBinaryMask(self,plotAxis=None,color='#ff0000',alpha=1):
        '''
        return display image (RGBA uint8 format) which can be plotted by plt.imshow, alpha: transparency 0-1
        '''
        mask = self.getBinaryMask()
        displayImg = pt.binary2RGBA(mask,foregroundColor=color,backgroundColor='#000000',foregroundAlpha=int(alpha*255),backgroundAlpha=0)
        if plotAxis is None: f=plt.figure();plotAxis=f.add_subplot(111);plotAxis.imshow(displayImg,interpolation='nearest')
        return displayImg


    def plotBinaryMaskBorder(self,**kwargs):
        pt.plotMask(self.getNanMask(),**kwargs)


    def toH5Group(self, h5Group):
        '''
        add attributes and dataset to a h5 data group
        '''
        h5Group.attrs['dimension'] = self.dimension
        if self.pixelSize is None: h5Group.attrs['pixelSize'] = 'None'
        else: h5Group.attrs['pixelSize'] = self.pixelSize
        if self.pixelSizeUnit is None: h5Group.attrs['pixelSizeUnit'] = 'None'
        else: h5Group.attrs['pixelSizeUnit'] = self.pixelSizeUnit

        dataDict = dict(self.__dict__)
        _ = dataDict.pop('dimension');_ = dataDict.pop('pixelSize');_ = dataDict.pop('pixelSizeUnit')
        for key, value in dataDict.iteritems():
            if value is None: h5Group.create_dataset(key,data='None')
            else: h5Group.create_dataset(key,data=value)



class WeightedROI(ROI):

    def __init__(self, mask, pixelSize = None, pixelSizeUnit = None):
        super(WeightedROI,self).__init__(mask, pixelSize = pixelSize, pixelSizeUnit = pixelSizeUnit)
        self.weights = mask[self.pixels]


    def getWeightedMask(self):
        mask = np.zeros(self.dimension,dtype=np.float32)
        mask[self.pixels] = self.weights
        return mask


    def getWeightedNanMask(self):
        mask = np.zeros(self.dimension,dtype=np.float32)
        mask[:]=np.nan
        mask[self.pixels] = self.weights
        return mask


    def getWeightedCenter(self):
        pixelCor = np.array(self.pixels,dtype=np.float)
        center = np.sum(np.multiply(pixelCor,np.array(self.weights)),axis=1)/np.sum(self.weights)
        return center

    def getWeightedCenterInCoordinate(self,yCor,xCor):
        '''
        return weighted center of the ROI in the coordinate system defined by np.meshgrid(xCor, yCor)
        '''
        weightMask = self.getWeightedMask()
        xMap, yMap = np.meshgrid(xCor, yCor)
        xCenter = np.sum((xMap*weightMask).flatten())/np.sum(weightMask.flatten())
        yCenter = np.sum((yMap*weightMask).flatten())/np.sum(weightMask.flatten())
        return [yCenter, xCenter]


    def getWeightedTrace(self, mov):
        mask = self.generateWeightedMask()
        trace = np.multiply(mov,np.array([mask])).sum(axis=1).sum(axis=1)
        return trace


    def plotWeightedMask(self,plotAxis=None,color='#ff0000'):
        '''
        return display image (RGBA uint8 format) which can be plotted by plt.imshow
        '''
        mask = self.getWeightedMask()
        displayImg = pt.scalar2RGBA(mask,color=color)
        if plotAxis is None: f=plt.figure(); plotAxis=f.add_subplot(111); plotAxis.imshow(displayImg,interpolation='nearest')
        return displayImg


    def getTrace(self,mov):
        '''
        return trace of this ROI in a given movie
        '''
        weightedMask = self.getWeightedMask()
        trace = np.multiply(mov,np.array([weightedMask])).sum(axis=1).sum(axis=1)
        return trace



class SpatialTemporalReceptiveField(object):
    '''
    class of spatial temporal receptive field represented by traces for each specified retinotopic location
    '''

    def __init__(self,locations,signs,traces,time,name=None):
        '''
        locations: list of retinotopic locations mapped, array([altitude, azimuth])
        signs: list of signs for each location
        tracesON: list of traces for each location
                  list of 2-d array, each row: a single trace, each column: a single time point
        time: time axis for trace
        '''

        self.time = time
        self.name = name
        dtype = [('altitude',float),('azimuth',float),('sign',int),('traces',list)]
        values = [ (location[0], location[1], signs[i], traces[i]) for i, location in enumerate(locations)]
        if not values: raise ValueError, 'Can not find input traces!'

        self.data = np.array(values,dtype=dtype)
        self.sortData()


    def mergeDuplication(self):
        #todo: merge traces with same retinotopic loacation
        pass


    def sortData(self):
        self.data = np.sort(self.data,order=['sign','altitude','azimuth'])


    def getDataType(self):
        return self.data.dtype


    def getLocations(self):
        return list(np.array([self.data['altitude'],self.data['azimuth'],self.data['sign']]).transpose())


    def addTraces(self,locations,signs,traces):

        '''
        add traces to existing receptive field
        '''

        dtype = [('altitude',float),('azimuth',float),('sign',int),('traces',list)]

        values = [ (location[0], location[1], signs[i], traces[i]) for i, location in enumerate(locations)]
        if not values: raise ValueError, 'Can not find input traces!'

        locations = [np.array([x[0],x[1],x[2]]) for x in values]

        objLocations = self.getLocations()

        traceTuplesNeedToBeAdded = []

        for i, location in enumerate(locations):
            newTraceTuple = values[i]
            findSameLocation = False

            for j, objLocation in enumerate(objLocations):

                if np.array_equal(location,objLocation):
                    findSameLocation = True
                    objTraceItem = self.data[j]
                    objTraceItem['traces'] = objTraceItem['traces'] + newTraceTuple[3]

            if findSameLocation == False:
                traceTuplesNeedToBeAdded.append(tuple(newTraceTuple))

        if traceTuplesNeedToBeAdded:
            self.data = np.concatenate((self.data,np.array(traceTuplesNeedToBeAdded,dtype=dtype)),axis=0)

        self.sortData()


    def toH5Group(self, h5Group):

        h5Group.attrs['time'] = self.time
        h5Group.attrs['time_unit'] = 'second'
        h5Group.attrs['retinotopic_location_unit'] = 'degree'
        h5Group.attrs['trace_data_type'] = 'dF_over_F'
        h5Group.attrs['trace_data_unit'] = '%'
        h5Group.attrs['trace_representation_axis'] = 0
        h5Group.attrs['trace_time_point_axis'] = 1

        for i in range(len(self.data)):
            locationName = 'trace'+ft.int2str(i,4)
            trace = h5Group.create_dataset(locationName,data=self.data[i]['traces'], dtype='f')
            trace.attrs['altitude'] = self.data[i]['altitude']
            trace.attrs['azimuth'] = self.data[i]['azimuth']
            trace.attrs['sign'] = self.data[i]['sign']


    def plotTraces(self,f=None,figSize=(10,10),yRange=(0,20),**kwargs):

        indexLists, axisLists = self._getAxisLayout(f,figSize,yRange,**kwargs)

        for i, axisList in enumerate(axisLists):
            for j, axis in enumerate(axisList):
                indexList = indexLists[i][j]
                # axis.set_axis_off()
                axis.set_xticks([]);axis.set_yticks([])
                for pos in ['top','bottom','left','right']:
                    axis.spines[pos].set_linewidth(0.5)
                    axis.spines[pos].set_color('#888888')
                axis.plot([0,0],yRange,'--',color='#888888',lw=0.5)

                for index in indexList:
                    if index:
                        traces = self.data[index]['traces']
                        meanTrace = np.mean(traces,axis=0)
                        semTrace = np.std(traces,axis=0)/np.sqrt(float(len(traces)))
                        if self.data[index]['sign'] == 1: color = '#ff0000'
                        if self.data[index]['sign'] == -1: color = '#0000ff'
                        axis.fill_between(self.time,meanTrace-semTrace,meanTrace+semTrace,facecolor=color,linewidth=0,alpha=0.5)
                        axis.plot(self.time,meanTrace,'-',color=color,lw=1)

        return f


    def _getAxisLayout(self,f=None,figSize=(10,10),yRange=(0,20),**kwargs):

        locations = np.array(self.getLocations())
        altPositions = np.sort(np.unique(locations[:,0]))[::-1]; aziPositions = np.sort(np.unique(locations[:,1]))
        indexLists = [ [[] for aziPosition in aziPositions] for altPosition in altPositions]

        if f is None: f=plt.figure(figsize=figSize)
        f.suptitle('cell:'+str(self.name)+'; xrange:['+str(self.time[0])[0:6]+','+str(self.time[-1])[0:6]+']; yrange:'+str(yRange))

        axisLists = pt.tileAxis(f,len(altPositions),len(aziPositions),**kwargs)

        for i, altPosition in enumerate(altPositions):
            for j, aziPosition in enumerate(aziPositions):
                axisLists[i][j].text(self.time[0],yRange[1],str(altPosition)+';'+str(aziPosition),ha='left',va='top',fontsize=10)
                axisLists[i][j].set_xlim([self.time[0],self.time[-1]])
                axisLists[i][j].set_ylim(yRange)

                for k, location in enumerate(locations):
                    if location[0] == altPosition and location[1] == aziPosition:
                        indexLists[i][j].append(k)


        return indexLists, axisLists


    def getAmplitudeMap(self,timeWindow=(0,0.5)):
        '''
        return 2d receptive field map and altitude and azimuth coordinates
        each pixel in the map represent mean amplitute of traces within the window defined by timeWindow
        '''

        windowIndex = np.logical_and(self.time>=timeWindow[0], self.time<=timeWindow[1])

        indON,indOFF,allAltPos,allAziPos = self._sortIndex()

        ampON = np.zeros(indON.shape); ampON[:]=np.nan; ampOFF = ampON.copy()

        for i in np.ndindex(indON.shape):
            traceIndON = indON[i]; traceIndOFF = indOFF[i]
            if traceIndON is not None: ampON[i] = np.mean(np.mean(self.data[traceIndON]['traces'],axis=0)[windowIndex])
            if traceIndOFF is not None: ampOFF[i] = np.mean(np.mean(self.data[traceIndOFF]['traces'],axis=0)[windowIndex])

        return ampON, ampOFF, allAltPos, allAziPos


    def getZscoreMap(self,timeWindow=(0,0.5)):
        '''
        return 2d receptive field and altitude and azimuth coordinates
        each pixel in the map represent Z score of mean amplitute of traces within the window defined by timeWindow
        '''

        ampON, ampOFF, allAltPos, allAziPos = self.getAmplitudeMap(timeWindow)
        return ia.zscore(ampON), ia.zscore(ampOFF), allAltPos, allAziPos


    def getZscoreROIs(self,timeWindow=(0,0.5),zscoreThr=2):
        '''
        return ON, OFF and combined receptive field rois in the format of WeightedROI object

        Amplitude for each pixel was calculated as mean dF over F signal trace within the timeWindow
        mask of ON and OFF receptive field was generated by cutting zscore map by zscoreThr
        Tombined mask is the sum of ON and OFF weighted mask

        The sampled altitude positions and azimuth positions are also returned. The receptive field space coordinates
        were defined as np.meshgrid(allAltPos,allAziPos)
        '''
        zscoreON, zscoreOFF, allAltPos, allAziPos = self.getZscoreMap(timeWindow)
        zscoreROION = getPeakWeightedROI(zscoreON,zscoreThr)
        zscoreROIOFF = getPeakWeightedROI(zscoreOFF,zscoreThr)
        zscoreROIALL = WeightedROI(zscoreROION.getWeightedMask()+zscoreROIOFF.getWeightedMask())

        return zscoreROION,zscoreROIOFF,zscoreROIALL,allAltPos,allAziPos


    def getZscoreROICenters(self,timeWindow=(0,0.5),zscoreThr=2):
        '''
        return retinotopic location of ON subfield, OFF subfield and combined receptive field

        zscore ROIs was generated by the method getZscoreROIs()
        '''
        zscoreROION,zscoreROIOFF,zscoreROIALL,allAltPos,allAziPos = self.getZscoreROIs(timeWindow,zscoreThr)
        centerON = zscoreROION.getWeightedCenterInCoordinate(allAltPos,allAziPos)
        centerOFF = zscoreROIOFF.getWeightedCenterInCoordinate(allAltPos,allAziPos)
        centerALL = zscoreROIALL.getWeightedCenterInCoordinate(allAltPos,allAziPos)
        return centerON, centerOFF, centerALL

    def _sortIndex(self):
        '''
        return ON and OFF index matrices for all combination of sampled retinotopic locations along with retinotopic
        coordinates
        '''

        allAltPos = np.array(sorted(list(set(list(self.data['altitude'])))))[::-1]
        allAziPos = np.array(sorted(list(set(list(self.data['azimuth'])))))

        indON = [[None for azi in allAziPos] for alt in allAltPos]; indOFF = [[None for azi in allAziPos] for alt in allAltPos]

        for i, traceItem in enumerate(self.data):
            alt = traceItem['altitude'];azi = traceItem['azimuth'];sign = traceItem['sign']
            for j, altPos in enumerate(allAltPos):
                for k, aziPos in enumerate(allAziPos):
                    if alt==altPos and azi==aziPos:
                        if sign==1:
                            if indON[j][k] is not None: raise LookupError, 'Duplication of trace items found at location:'+str([alt, azi])+'; sign: 1!'
                            else: indON[j][k]=i

                        if sign==-1:
                            if indOFF[j][k] is not None: raise LookupError, 'Duplication of trace items found at location:'+str([alt, azi])+'; sign:-1!'
                            else: indOFF[j][k]=i

        indON = np.array([np.array(x) for x in indON]); indOFF = np.array([np.array(x) for x in indOFF])

        return indON,indOFF,allAltPos,allAziPos















if __name__=='__main__':

    plt.ioff()

    #=====================================================================
    # a = np.zeros((10,10))
    # a[5:7,3:6]=1
    # a[8:9,7:10]=np.nan
    # roi = ROI(a)
    # plt.imshow(roi.getBinaryMask(),interpolation='nearest')
    # plt.show()
    # print roi.getCenter()
    #=====================================================================

    #=====================================================================
    # mov = np.random.rand(5,4,4)
    # mask = np.zeros((4,4))
    # mask[2,3]=1
    # trace1 = mov[:,2,3]
    # roi = ROI(mask)
    # trace2 = roi.getTrace(mov)
    # assert(np.array_equal(trace1,trace2))
    #=====================================================================

    #=====================================================================
    # aa = np.random.rand(5,5)
    # mask = np.zeros((5,5))
    # mask[2,3]=aa[2,3]
    # mask[1,4]=aa[1,4]
    # mask[3,4]=aa[3,4]
    # roi = WeightedROI(mask)
    # center = roi.getCenter()
    # assert roi.getCenter()[0] == (2*aa[2,3]+1*aa[1,4]+3*aa[3,4])/(aa[2,3]+aa[1,4]+aa[3,4])
    #=====================================================================

    #=====================================================================
    # aa = np.zeros((50,50))
    # aa[15:20,30:35] = np.random.rand(5,5)
    # roi1 = ROI(aa)
    # _ = roi1.plotBinaryMaskBorder()
    # _ = roi1.plotBinaryMask()
    # roi2 = WeightedROI(aa)
    # _ = roi2.plotBinaryMaskBorder()
    # _ = roi2.plotBinaryMask()
    # _ = roi2.plotWeightedMask()
    # plt.show()
    #=====================================================================

    #=====================================================================
    # aa = np.zeros((5,5))
    # aa[1:3,2:4] = 0.5
    # plt.imshow(aa, interpolation='nearest')
    # plt.show()
    #
    # roi = WeightedROI(aa)
    # print roi.getWeightedCenter()
    # print roi.getWeightedCenterInCoordinate(range(2,7),range(1,6))
    #=====================================================================

    #=====================================================================
    # pklPath = r"Z:\Jun\150610-M160809\SparseNoise_5x5_003\150610174646-SparseNoise-mouse160809-Jun-notTriggered.pkl"
    # allOnsetInd, onsetIndWithLocationSign = getSparseNoiseOnsetIndex(ft.loadFile(pklPath))
    # print allOnsetInd[0:10]
    # print onsetIndWithLocationSign[0:3]
    #=====================================================================

    #=====================================================================
    # locations = [[3.0, 4.0], [3.0, 5.0], [2.0, 4.0], [2.0, 5.0],[3.0, 4.0], [3.0, 5.0], [2.0, 4.0], [2.0, 5.0]]
    # signs = [1,1,1,1,-1,-1,-1,-1]
    # traces=[[np.arange(4)],[np.arange(1,5)],[np.arange(2,6)],[np.arange(3,7)],[np.arange(5,9)],[np.arange(6,10)],[np.arange(7,11)],[np.arange(8,12)]]
    # time = np.arange(4,8)
    #
    # STRF = SpatialTemporalReceptiveField(locations,signs,traces,time)
    #
    # print STRF.data
    # print STRF.getLocations()
    #
    # newLocations = [[location[0]+1,location[1]+1] for location in locations[0:4]]
    # newSigns = [1,1,1,1]
    # STRF.addTraces(newLocations,newSigns,traces[0:4])
    #
    # print STRF.data
    #
    # _ = STRF.plotRawTraces()
    # plt.show()
    #=====================================================================

    #=====================================================================
    # testFile = h5py.File(r"C:\JunZhuang\labwork\data\python_temp_folder\test.hdf5")
    # STRFGroup = testFile.create_group('spatial_temporal_receptive_field')
    # STRF.toH5Group(STRFGroup)
    # testFile.close()
    #=====================================================================

    #=====================================================================
    # filePath = r"C:\JunZhuang\labwork\data\python_temp_folder\test.hdf5"
    # h5File = h5py.File(filePath)
    # STRF = load_STRF_FromH5(h5File['spatial_temporal_receptive_field'])
    # h5File.close()
    # print STRF.data
    #=====================================================================

    #=====================================================================
    # f = h5py.File(r"E:\data2\2015-07-02-150610-M160809-2P_analysis\cells_test.hdf5")
    # STRF = load_STRF_FromH5(f['cell0003']['spatial_temporal_receptive_field'])
    # STRF.plotTraces(figSize=(15,10),yRange=[-5,50],columnSpacing=0.002,rowSpacing=0.002)
    # plt.show()
    #=====================================================================

    #=====================================================================
    # f = h5py.File(r"E:\data2\2015-07-02-150610-M160809-2P_analysis\cells_test.hdf5")
    # STRF = load_STRF_FromH5(f['cell0003']['spatial_temporal_receptive_field'])
    # ampON, ampOFF, altPos, aziPos = STRF.getAmplitudeMap()
    # plot2DReceptiveField(ampON,altPos,aziPos,cmap='gray_r',interpolation='nearest')
    # plt.show()
    #=====================================================================

    #=====================================================================
    # f = h5py.File(r"E:\data2\2015-07-02-150610-M160809-2P_analysis\cells_test.hdf5")
    # STRF = load_STRF_FromH5(f['cell0003']['spatial_temporal_receptive_field'])
    # zscoreON, zscoreOFF, altPos, aziPos = STRF.getZscoreMap()
    # plot2DReceptiveField(zscoreON,altPos,aziPos,cmap='gray_r',vmin=-1,vmax=3,interpolation='nearest')
    # plt.show()
    #=====================================================================

    #=====================================================================
    f = h5py.File(r"E:\data2\2015-07-02-150610-M160809-2P_analysis\cells_test.hdf5")
    STRF = load_STRF_FromH5(f['cell0003']['spatial_temporal_receptive_field'])
    zscoreROION,zscoreROIOFF,zscoreROIALL,allAltPos,allAziPos = STRF.getZscoreROIs()
    fig = plt.figure(figsize=(15,4))
    ax1 = fig.add_subplot(131);plot2DReceptiveField(zscoreROION.getWeightedMask(),allAltPos,allAziPos,ax1,cmap='gray_r',vmin=0,vmax=3,interpolation='nearest')
    ax2 = fig.add_subplot(132);plot2DReceptiveField(zscoreROIOFF.getWeightedMask(),allAltPos,allAziPos,ax2,cmap='gray_r',vmin=0,vmax=3,interpolation='nearest')
    ax3 = fig.add_subplot(133);plot2DReceptiveField(zscoreROIALL.getWeightedMask(),allAltPos,allAziPos,ax3,cmap='gray_r',vmin=0,vmax=3,interpolation='nearest')
    plt.show()

    print STRF.getZscoreROICenters()
    #=====================================================================


    print 'for debug...'