#!/usr/bin/env python
from psychopy import core, visual, event

#create a window to draw in
myWin = visual.Window((800,800), monitor='testMonitor',allowGUI=False, color=(-1,-1,-1))
myWin._haveShaders=False

#INITIALISE SOME STIMULI
beach = visual.ImageStim(myWin, image='beach.jpg', flipVert=True, pos=(0,4.50), units='deg')
faceRGB = visual.ImageStim(myWin,image='face.jpg', mask=None,
    pos=(50,-50), 
    size=None,#will be the size of the original image in pixels
    units='pix', interpolate=True,
    autoLog=False)#this stim changes too much for autologging to be useful
print "original image size:", faceRGB.origSize
faceALPHA = visual.GratingStim(myWin,pos=(-0.7,-0.2),
    tex="sin",mask="face.jpg",
    color=[1.0,1.0,-1.0],
    size=(0.5,0.5), units="norm",
    autoLog=False)#this stim changes too much for autologging to be useful
    
message = visual.TextStim(myWin,pos=(-0.95,-0.95),
    text='[Esc] to quit', color='white', alignHoriz='left', alignVert='bottom')

trialClock = core.Clock()
t=lastFPSupdate=0
myWin.setRecordFrameIntervals()
while True:
    t=trialClock.getTime()
    #Images can be manipulated on the fly
    faceRGB.setOri(1,'+')#advance ori by 1 degree
    faceRGB.draw()
    faceALPHA.setPhase(0.01,"+")#advance phase by 1/100th of a cycle
    faceALPHA.draw()
    beach.draw()
    
    #update fps every second
    if t-lastFPSupdate>1.0:
        lastFPS = myWin.fps()
        lastFPSupdate=t
        message.setText("%ifps, [Esc] to quit" %lastFPS)
    message.draw()

    myWin.flip()

    #handle key presses each frame
    for keys in event.getKeys():
        if keys in ['escape','q']:
            print myWin.fps()
            myWin.close()
            core.quit()
    event.clearEvents('mouse')#only really needed for pygame windows
