import matplotlib.pyplot as plt
import corticalmapping.VisualStim2 as vs


mouseID = 'TEST' #'147861' #'TEST'
userID = 'Jun'
numOfTrials = 30 # 20
color = 1. # [-1., 1.]
background = -1. # [-1. 1.]
center = (60., 10.) # (azi, alt), degree
radius = 10. # degree
duration = 0.05 # second
isTriggered = True


# do not change the following code
refreshRate = 60.
psychopyMonitor = 'smartTVgamma' #'smartTVgamma'
logFolder = r'C:\data'
backupFolder = r'\\W7DTMJ38BBB\data'

mon=vs.Monitor(resolution=(1080, 1920),
               dis=15.3,
               monWcm=88.8,
               monHcm=50.1,
               C2Tcm=31.1,
               C2Acm=41.91,
               monTilt=26.56,
               downSampleRate=5,
               refreshRate=refreshRate)
                  
#mon.plot_map()
#plt.show()                  
                  
indicator=vs.Indicator(mon,
                       width_cm=3.,
                       height_cm=3.,
                       position = 'southeast',
                       isSync=True,
                       freq=1.)

stim = vs.FlashingCircle(mon,
                         indicator,
                         coordinate='degree', # 'degree' or 'linear'
                         center=center, # center coordinate of the circle (degree)
                         radius=radius, # radius of the circle
                         color=color, # color of the circle [-1: 1]
                         iteration=1, # total number of flashes
                         flashFrame=int(duration*refreshRate), # frame number for display circle of each flash
                         preGapDur=2., # gap frame number before flash
                         postGapDur=3., # gap frame number after flash
                         background=background)

ds = vs.DisplaySequence(logdir=logFolder,
                        backupdir=backupFolder,
                        displayIteration=numOfTrials,
                        psychopyMonitor=psychopyMonitor,
                        displayOrder=1,
                        mouseid=mouseID,
                        userid=userID,
                        isInterpolate=False,
                        isTriggered=isTriggered,
                        triggerNIDev='Dev1',
                        triggerNIPort=1,
                        triggerNILine=0,
                        triggerType="NegativeEdge",
                        isSyncPulse=True,
                        syncPulseNIDev='Dev1',
                        syncPulseNIPort=1,
                        syncPulseNILine=1,
                        displayScreen=1,
                        initialBackgroundColor=0.,
                        isVideoRecord=True,
                        videoRecordIP='w7dtmj007lhu',
                        videoRecordPort=10000,
                        displayControlIP = 'localhost',
                        displayControlPort = 10002,
                        fileNumNIDev = 'Dev1',
                        fileNumNIPort = 0,
                        fileNumNILines = '0:7')

ds.set_stim(stim)

ds.trigger_display()

plt.show()