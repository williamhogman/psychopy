# -*- coding: utf-8 -*-
"""To handle input from keyboard, mouse and joystick (joysticks require pygame to be installed).
See demo_mouse.py and i{demo_joystick.py} for examples
"""
# Part of the PsychoPy library
# Copyright (C) 2012 Jonathan Peirce
# Distributed under the terms of the GNU General Public License (GPL).

# 01/2011 modified by Dave Britton to get mouse event timing

import sys, time, copy
import psychopy.core, psychopy.misc
from psychopy import logging
from psychopy.constants import *
import string, numpy

#try to import pyglet & pygame and hope the user has at least one of them!
try:
    from pygame import mouse, locals, joystick, display
    import pygame.key
    import pygame.event as evt
    havePygame = True
except:
    havePygame = False

try:
    import pyglet
    havePyglet = True
except:
    havePyglet = False
if havePygame: usePygame=True#will become false later if win not initialised
else: usePygame=False

if havePyglet:

    global _keyBuffer
    _keyBuffer = []
    global mouseButtons
    mouseButtons = [0,0,0]
    global mouseWheelRel
    mouseWheelRel = numpy.array([0.0,0.0])
    global mouseClick # list of 3 clocks that are reset on mouse button presses
    mouseClick = [psychopy.core.Clock(),psychopy.core.Clock(),psychopy.core.Clock()]
    global mouseTimes
    mouseTimes = [0.0,0.0,0.0] # container for time elapsed from last reset of mouseClick[n] for any button pressed
    global mouseMove # clock for tracking time of mouse movement, reset when mouse is moved
    mouseMove = psychopy.core.Clock() # reset on mouse motion
    #global eventThread
    #eventThread = _EventDispatchThread()
    #eventThread.start()

def _onPygletKey(symbol, modifiers, emulated=False):
    """handler for on_key_press pyglet events, or call directly to emulate a key press
    
    Appends a tuple with (keyname, timepressed) into the global _keyBuffer. The
    _keyBuffer can then be accessed as normal using event.getKeys(), .waitKeys(),
    clearBuffer(), etc.
    
    J Gray 2012: Emulated means add a key (symbol) to the buffer virtually.
    This is useful for fMRI_launchScan, and for unit testing (in testTheApp)
    Logging distinguished EmulatedKey events from real Keypress events.
    For emulation, the key added to the buffer is unicode(symbol), instead of
    pyglet.window.key.symbol_string(symbol)
    """
    keyTime=psychopy.core.getTime() #capture when the key was pressed
    if emulated:
        thisKey = unicode(symbol)
        keySource = 'EmulatedKey'
    else:
        thisKey = pyglet.window.key.symbol_string(symbol).lower() #convert symbol into key string
        #convert pyglet symbols to pygame forms ( '_1'='1', 'NUM_1'='[1]')
        thisKey = thisKey.lstrip('_').lstrip('NUM_')
        keySource = 'Keypress'
    _keyBuffer.append( (thisKey,keyTime) ) # tuple
    logging.data("%s: %s" % (keySource, thisKey))

def _onPygletMousePress(x,y, button, modifiers):
    global mouseButtons, mouseClick, mouseTimes
    if button == pyglet.window.mouse.LEFT:
        mouseButtons[0]=1
        mouseTimes[0]= psychopy.core.getTime()-mouseClick[0].timeAtLastReset
        label='Left'
    if button == pyglet.window.mouse.MIDDLE:
        mouseButtons[1]=1
        mouseTimes[1]= psychopy.core.getTime()-mouseClick[1].timeAtLastReset
        label='Middle'
    if button == pyglet.window.mouse.RIGHT:
        mouseButtons[2]=1
        mouseTimes[2]= psychopy.core.getTime()-mouseClick[2].timeAtLastReset
        label='Right'
    logging.data("Mouse: %s button down, pos=(%i,%i)" %(label, x,y))

def _onPygletMouseRelease(x,y, button, modifiers):
    global mouseButtons
    if button == pyglet.window.mouse.LEFT:
        mouseButtons[0]=0
        label='Left'
    if button == pyglet.window.mouse.MIDDLE:
        mouseButtons[1]=0
        label='Middle'
    if button == pyglet.window.mouse.RIGHT:
        mouseButtons[2]=0
        label='Right'
    logging.data("Mouse: %s button up, pos=(%i,%i)" %(label, x,y))

def _onPygletMouseWheel(x,y,scroll_x, scroll_y):
    global mouseWheelRel
    mouseWheelRel = mouseWheelRel+numpy.array([scroll_x, scroll_y])
    logging.data("Mouse: wheel shift=(%i,%i), pos=(%i,%i)" %(scroll_x, scroll_y,x,y))

def _onPygletMouseMotion(x, y, dx, dy): # will this work? how are pyglet event handlers defined?
    global mouseMove
    # mouseMove is a core.Clock() that is reset when the mouse moves
    # default is None, but start and stopMoveClock() create and remove it, mouseMove.reset() resets it by hand
    if mouseMove: mouseMove.reset()

def startMoveClock():
    global mouseMove
    mouseMove=psychopy.core.Clock()

def stopMoveClock():
    global mouseMove
    mouseMove=None

def resetMoveClock():
    global mouseMove
    if mouseMove: mouseMove.reset()
    else: startMoveClock()

#class Keyboard:
#    """The keyboard class is currently just a helper class to allow common
#    attributes with other objects (like mouse and stimuli). In particular
#    it allows storage of the .status property (NOT_STARTED, STARTED, STOPPED).

#    It isn't really needed for most users - the functions it supports (e.g.
#    getKeys()) are directly callable from the event module.

#    Note that multiple Keyboard instances will not keep separate buffers.

#    """
#    def __init__(self):
#        self.status=NOT_STARTED
#    def getKeys(keyList=None, timeStamped=False):
#        return getKeys(keyList=keyList, timeStamped=timeStamped)
#    def waitKeys(maxWait = None, keyList=None):
#        return def waitKeys(maxWait = maxWait, keyList=keyList)

def getKeys(keyList=None, timeStamped=False):
    """Returns a list of keys that were pressed.

    :Parameters:
        keyList : **None** or []
            Allows the user to specify a set of keys to check for.
            Only keypresses from this set of keys will be removed from the keyboard buffer.
            If the keyList is None all keys will be checked and the key buffer will be cleared
            completely. NB, pygame doesn't return timestamps (they are always 0)
        timeStamped : **False** or True or `Clock`
            If True will return a list of
            tuples instead of a list of keynames. Each tuple has (keyname, time).
            If a `core.Clock` is given then the time will be relative to the `Clock`'s last reset

    :Author:
        - 2003 written by Jon Peirce
        - 2009 keyList functionality added by Gary Strangman
        - 2009 timeStamped code provided by Dave Britton
    """
    keys=[]


    if havePygame and display.get_init():#see if pygame has anything instead (if it exists)
        for evts in evt.get(locals.KEYDOWN):
            keys.append( (pygame.key.name(evts.key),0) )#pygame has no keytimes

    elif havePyglet:
        #for each (pyglet) window, dispatch its events before checking event buffer
        wins = pyglet.window.get_platform().get_default_display().get_windows()
        for win in wins: win.dispatch_events()#pump events on pyglet windows

        global _keyBuffer
        if len(_keyBuffer)>0:
            #then pyglet is running - just use this
            keys = _keyBuffer
    #        _keyBuffer = []  # DO /NOT/ CLEAR THE KEY BUFFER ENTIRELY

    if keyList==None:
        _keyBuffer = [] #clear buffer entirely
        targets=keys  # equivalent behavior to getKeys()
    else:
        nontargets = []
        targets = []
        # split keys into keepers and pass-thrus
        for key in keys:
            if key[0] in keyList:
                targets.append(key)
            else:
                nontargets.append(key)
        _keyBuffer = nontargets  # save these

    #now we have a list of tuples called targets
    #did the user want timestamped tuples or keynames?
    if timeStamped==False:
        keyNames = [k[0] for k in targets]
        return keyNames
    elif hasattr(timeStamped, 'timeAtLastReset'):
        relTuple = [(k[0],k[1]-timeStamped.timeAtLastReset) for k in targets]
        return relTuple
    elif timeStamped==True:
        return targets

def waitKeys(maxWait = None, keyList=None):
    """
    Halts everything (including drawing) while awaiting
    input from keyboard. Then returns *list* of keys pressed. Implicitly clears
    keyboard, so any preceding keypresses will be lost.

    Optional arguments specify maximum wait period and which keys to wait for.

    Returns None if times out.
    """

    #NB pygame.event does have a wait() function that will
    #do this and maybe leave more cpu idle time?
    key=None
    clearEvents('keyboard')#so that we only take presses from here onwards.
    if maxWait!=None and keyList!=None:
        #check keylist AND timer
        timer = psychopy.core.Clock()
        while key==None and timer.getTime()<maxWait:
            if havePyglet:
                wins = pyglet.window.get_platform().get_default_display().get_windows()
                for win in wins: win.dispatch_events()#pump events on pyglet windows
            keys = getKeys()
            #check if we got a key in list
            if len(keys)>0 and (keys[0] in keyList):
                key = keys[0]

    elif keyList!=None:
        #check the keyList each time there's a press
        while key==None:
            if havePyglet:
                wins = pyglet.window.get_platform().get_default_display().get_windows()
                for win in wins: win.dispatch_events()#pump events on pyglet windows
            keys = getKeys()
            #check if we got a key in list
            if len(keys)>0 and (keys[0] in keyList):
                key = keys[0]

    elif maxWait!=None:
        #onyl wait for the maxWait
        timer = psychopy.core.Clock()
        while key==None and timer.getTime()<maxWait:
            if havePyglet:
                wins = pyglet.window.get_platform().get_default_display().get_windows()
                for win in wins: win.dispatch_events()#pump events on pyglet windows
            keys = getKeys()
            #check if we got a key in list
            if len(keys)>0:
                key = keys[0]

    else: #simply take the first key we get
        while key==None:
            if havePyglet:
                wins = pyglet.window.get_platform().get_default_display().get_windows()
                for win in wins: win.dispatch_events()#pump events on pyglet windows
            keys = getKeys()
            #check if we got a key in list
            if len(keys)>0:
                key = keys[0]

    #after the wait period or received a valid keypress
    if key:
        logging.data("Key pressed: %s" %key)
        return [key]#need to convert back to a list
    else:
        return None #no keypress in period

def xydist(p1=[0.0,0.0],p2=[0.0,0.0]):
    """Helper function returning the cartesian distance between p1 and p2
    """
    return numpy.sqrt(pow(p1[0]-p2[0],2)+pow(p1[1]-p2[1],2))

class Mouse:
    """Easy way to track what your mouse is doing.
    It needn't be a class, but since Joystick works better
    as a class this may as well be one too for consistency

    Create your `visual.Window` before creating a Mouse.

    :Parameters:
        visible : **True** or False
            makes the mouse invisbile if necessary
        newPos : **None** or [x,y]
            gives the mouse a particular starting position (pygame `Window` only)
        win : **None** or `Window`
            the window to which this mouse is attached (the first found if None provided)

    """
    def __init__(self,
                 visible=True,
                 newPos=None,
                 win=None):
        self.visible=visible
        self.lastPos = None
        self.prevPos = None # used for motion detection and timing
        self.win=win
        self.status=None#can be set to STARTED, NOT_STARTED etc for builder
        self.mouseClock=psychopy.core.Clock() # used for movement timing
        self.movedistance=0.0
        #if pygame isn't initialised then we must use pyglet
        global usePygame
        if (havePygame and not pygame.display.get_init()):
            usePygame=False
        if not usePygame:
            global mouseButtons
            mouseButtons = [0,0,0]
        if newPos is not None: self.setPos(newPos)

    def setPos(self,newPos=(0,0)):
        """Sets the current postiion of the mouse (pygame only),
        in the same units as the :class:`~visual.Window` (0,0) is at centre

        :Parameters:
            newPos : (x,y) or [x,y]
                the new position on the screen

        """
        newPosPix = self._windowUnits2pix(numpy.array(newPos))
        if usePygame:
            newPosPix[1] = self.win.size[1]/2-newPosPix[1]
            newPosPix[0] = self.win.size[0]/2+newPosPix[0]
            mouse.set_pos(newPosPix)
        else: print "pyglet does not support setting the mouse position yet"

    def getPos(self):
        """Returns the current postion of the mouse,
        in the same units as the :class:`~visual.Window` (0,0) is at centre
        """
        if usePygame: #for pygame top left is 0,0
            lastPosPix = numpy.array(mouse.get_pos())
            #set (0,0) to centre
            lastPosPix[1] = self.win.size[1]/2-lastPosPix[1]
            lastPosPix[0] = lastPosPix[0]-self.win.size[0]/2
        else: #for pyglet bottom left is 0,0
            #use default window if we don't have one
            if self.win: w = self.win.winHandle
            else: w=pyglet.window.get_platform().get_default_display().get_windows()[0]
            #get position in window
            lastPosPix= numpy.array([w._mouse_x,w._mouse_y])
            #set (0,0) to centre
            lastPosPix = lastPosPix-self.win.size/2
        self.lastPos = self._pix2windowUnits(lastPosPix)
        return self.lastPos

    def mouseMoved(self, distance=None, reset=False):
        """Determine whether/how far the mouse has moved

        With no args returns true if mouse has moved at all since last getPos() call,
        or distance (x,y) can be set to pos or neg distances from x and y to see if moved either x or y that far from lastPos ,
        or distance can be an int/float to test if new coordinates are more than that far in a straight line from old coords.

        Retrieve time of last movement from self.mouseClock.getTime().

        Reset can be to 'here' or to screen coords (x,y) which allows measuring distance from there to mouse when moved.
        if reset is (x,y) and distance is set, then prevPos is set to (x,y) and distance from (x,y) to here is checked,
        mouse.lastPos is set as current (x,y) by getPos(), mouse.prevPos holds lastPos from last time mouseMoved was called
        """
        global mouseMove # clock that gets reset by pyglet mouse movement handler
        self.prevPos=copy.copy(self.lastPos) # needs initialization before getPos resets lastPos
        self.getPos() # sets self.lastPos to current position
        if not reset:
            if distance is None:
                    if self.prevPos[0] <> self.lastPos[0]: return True
                    if self.prevPos[1] <> self.lastPos[1]: return True
            else:
                    if isinstance(distance,int) or isinstance(distance,float):
                        self.movedistance=xydist(self.prevPos,self.lastPos)
                        if self.movedistance > distance: return True
                        else: return False
                    if (self.prevPos[0]+distance[0]) - self.lastPos[0] > 0.0: return True # moved on X-axis
                    if (self.prevPos[1]+distance[1]) - self.lastPos[0] > 0.0: return True # moved on Y-axis
            return False
        if isinstance(reset,bool) and reset:
            # reset is True so just reset the last move time, eg mouseMoved(reset=True) starts/zeroes the move clock
            mouseMove.reset() # resets the global mouseMove clock
            return False
        if reset=='here': # set to wherever we are
            self.prevPos=copy.copy(self.lastPos) # lastPos set in getPos()
            return False
        if hasattr(reset,'__len__'): # a tuple or list of (x,y)
            self.prevPos=copy.copy(reset) # reset to (x,y) to check movement from there
            if not distance: return False # just resetting prevPos, not checking distance
            else: # checking distance of current pos to newly reset prevposition
                if isinstance(distance,int) or isinstance(distance,float):
                    self.movedistance=xydist(self.prevPos,self.lastPos)
                    if self.movedistance > distance: return True
                    else: return False
                # distance is x,y tuple, to check if the mouse moved that far on either x or y axis
                # distance must be (dx,dy), and reset is (rx,ry), current pos (cx,cy): Is cx-rx > dx ?
                if abs(self.lastPos[0]-self.prevPos[0]) > distance[0]: return True # moved on X-axis
                if abs(self.lastPos[1]-self.prevPos[1]) > distance[1]: return True # moved on Y-axis
            return False
        return False

    def mouseMoveTime(self):
        global mouseMove
        if mouseMove:
                return psychopy.core.getTime()-mouseMove.timeAtLastReset
        else: return 0 # mouseMove clock not started

    def getRel(self):
        """Returns the new position of the mouse relative to the
        last call to getRel or getPos, in the same units as the :class:`~visual.Window`.
        """
        if usePygame:
            relPosPix=numpy.array(mouse.get_rel()) * [1,-1]
            return self._pix2windowUnits(relPosPix)
        else:
            #NB getPost() resets lastPos so MUST retrieve lastPos first
            if self.lastPos is None: relPos = self.getPos()
            else: relPos = -self.lastPos+self.getPos()#DON't switch to (this-lastPos)
            return relPos

    def getWheelRel(self):
        """Returns the travel of the mouse scroll wheel since last call.
        Returns a numpy.array(x,y) but for most wheels y is the only
        value that will change (except mac mighty mice?)
        """
        global mouseWheelRel
        rel = mouseWheelRel
        mouseWheelRel = numpy.array([0.0,0.0])
        return rel

    def getVisible(self):
        """Gets the visibility of the mouse (1 or 0)
        """
        if usePygame: return mouse.get_visible()
        else: print "Getting the mouse visibility is not supported under pyglet, but you can set it anyway"

    def setVisible(self,visible):
        """Sets the visibility of the mouse to 1 or 0

        NB when the mouse is not visible its absolute position is held
        at (0,0) to prevent it from going off the screen and getting lost!
        You can still use getRel() in that case.
        """
        if usePygame: mouse.set_visible(visible)
        else:
            if self.win: #use default window if we don't have one
                w = self.win.winHandle
            else:
                w=pyglet.window.get_platform().get_default_display().get_windows()[0]
            w.set_mouse_visible(visible)

    def clickReset(self,buttons=[0,1,2]):
        """Reset a 3-item list of core.Clocks use in timing button clicks.
           The pyglet mouse-button-pressed handler uses their timeAtLastReset when a button is pressed
           so the user can reset them at stimulus onset or offset to measure RT.
           The default is to reset all, but they can be reset individually as specified in buttons list
        """
        global mouseClick
        for c in buttons:
            mouseClick[c].reset()
            mouseTimes[c]=0.0

    def getPressed(self, getTime=False):
        """Returns a 3-item list indicating whether or not buttons 1,2,3 are currently pressed

        If `getTime=True` (False by default( then `getPressed` will return all buttons that
        have been pressed since the last call to `mouse.clickReset` as well as their
        time stamps::

            buttons = mouse.getPressed()
            buttons, times = mouse.getPressed(getTime=True)

        Typically you want to call :ref:`mouse.clickReset()` at stimulus onset, then
        after the button is pressed in reaction to it, the total time elapsed
        from the last reset to click is in mouseTimes. This is the actual RT,
        regardless of when the call to `getPressed()` was made.

        """
        global mouseButtons,mouseTimes
        if usePygame: return mouse.get_pressed()
        else:  #False: #havePyglet: # like in getKeys - pump the events
            #for each (pyglet) window, dispatch its events before checking event buffer
            wins = pyglet.window.get_platform().get_default_display().get_windows()
            for win in wins: win.dispatch_events()#pump events on pyglet windows

            #else:
            if not getTime: return mouseButtons
            else: return mouseButtons, mouseTimes

    def _pix2windowUnits(self, pos):
        if self.win.units=='pix': return pos
        elif self.win.units=='norm': return pos*2.0/self.win.size
        elif self.win.units=='cm': return psychopy.misc.pix2cm(pos, self.win.monitor)
        elif self.win.units=='deg': return psychopy.misc.pix2deg(pos, self.win.monitor)
    def _windowUnits2pix(self, pos):
        if self.win.units=='pix': return pos
        elif self.win.units=='norm': return pos*self.win.size/2.0
        elif self.win.units=='cm': return psychopy.misc.cm2pix(pos, self.win.monitor)
        elif self.win.units=='deg': return psychopy.misc.deg2pix(pos, self.win.monitor)


class BuilderKeyResponse():
    """Used in scripts created by the builder to keep track of a clock and
    the current status (whether or not we are currently checking the keyboard)
    """
    def __init__(self):
        self.status=NOT_STARTED
        self.keys=[] #the key(s) pressed
        self.corr=0 #was the resp correct this trial? (0=no, 1=yes)
        self.rt=[] #response time(s)
        self.clock=psychopy.core.Clock() #we'll use this to measure the rt

def clearEvents(eventType=None):
    """Clears all events currently in the event buffer.
    Optional argument, eventType, specifies only certain types to be
    cleared

    :Parameters:
        eventType : **None**, 'mouse', 'joystick', 'keyboard'
            If this is not None then only events of the given type are cleared
    """
    #pyglet
    if not havePygame or not display.get_init():

        #for each (pyglet) window, dispatch its events before checking event buffer
        wins = pyglet.window.get_platform().get_default_display().get_windows()
        for win in wins: win.dispatch_events()#pump events on pyglet windows
        if eventType=='mouse': return # pump pyglet mouse events but don't flush keyboard buffer
        global _keyBuffer
        _keyBuffer = []
        return

    #for pygame
    if eventType=='mouse':
        junk = evt.get([locals.MOUSEMOTION, locals.MOUSEBUTTONUP,
                        locals.MOUSEBUTTONDOWN])
    elif eventType=='keyboard':
        junk = evt.get([locals.KEYDOWN, locals.KEYUP])
    elif eventType=='joystick':
        junk = evt.get([locals.JOYAXISMOTION, locals.JOYBALLMOTION,
              locals.JOYHATMOTION, locals.JOYBUTTONUP, locals.JOYBUTTONDOWN])
    else:
        junk = evt.get()
