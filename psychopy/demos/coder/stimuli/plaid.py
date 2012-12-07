#!/usr/bin/env python
from psychopy import visual, logging, event, core

#create a window to draw in
myWin = visual.Window((600,600), allowGUI=False)
logging.console.setLevel(logging.DEBUG)

#INITIALISE SOME STIMULI
grating1 = visual.GratingStim(myWin,mask="gauss",
    color=[1.0,1.0,1.0],opacity=1.0,
    size=(1.0,1.0), sf=(4,0), ori = 45,
    autoLog=False)#this stim changes too much for autologging to be useful
grating2 = visual.GratingStim(myWin,mask="gauss",
    color=[1.0,1.0,1.0],opacity=0.5,
    size=(1.0,1.0), sf=(4,0), ori = 135,
    autoLog=False)#this stim changes too much for autologging to be useful

trialClock = core.Clock()
t = 0
while t<20:#quits after 20 secs

    t=trialClock.getTime()

    grating1.setPhase(1*t)  #drift at 1Hz
    grating1.draw()  #redraw it

    grating2.setPhase(2*t)    #drift at 2Hz
    grating2.draw()  #redraw it
    
    myWin.flip()          #update the screen

    #handle key presses each frame
    for keys in event.getKeys():
        if keys in ['escape','q']:
            core.quit()


