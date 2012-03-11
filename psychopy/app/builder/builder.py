# Part of the PsychoPy library
# Copyright (C) 2012 Jonathan Peirce
# Distributed under the terms of the GNU General Public License (GPL).

import wx
from wx.lib import platebtn, scrolledpanel
from wx.lib.expando import ExpandoTextCtrl, EVT_ETC_LAYOUT_NEEDED
#import wx.lib.agw.aquabutton as AB
import wx.aui
import sys, os, glob, copy, platform, shutil, traceback
import py_compile, codecs
import csv, numpy
import experiment, components
from psychopy.app import stdOutRich, dialogs
from psychopy import data, logging, misc, gui
import re
from tempfile import mkdtemp # to check code syntax
import cPickle
from psychopy.app.builder.experiment import _valid_var_re, _nonalphanumeric_re

from psychopy.constants import *

canvasColor=[200,200,200]#in prefs? ;-)
routineTimeColor=wx.Color(50,100,200, 200)
routineFlowColor=wx.Color(200,150,150, 255)
darkgrey=wx.Color(65,65,65, 255)
white=wx.Color(255,255,255, 255)
darkblue=wx.Color(30,30,150, 255)

class FileDropTarget(wx.FileDropTarget):
    """On Mac simply setting a handler for the EVT_DROP_FILES isn't enough.
    Need this too.
    """
    def __init__(self, builder):
        wx.FileDropTarget.__init__(self)
        self.builder = builder
    def OnDropFiles(self, x, y, filenames):
        logging.debug('PsychoPyBuilder: received dropped files: filenames')
        for filename in filenames:
            if filename.endswith('.psyexp'):
                self.builder.fileOpen(filename=filename)
            elif filename.lower().endswith('.py'):
                self.app.fileOpen(filename=filename)
            else:
                logging.warning('dropped file ignored: did not end in .psyexp')

class WindowFrozen(object):
    """
    Equivalent to wxWindowUpdateLocker.

    Usage::

        with WindowFrozen(wxControl):
          update multiple things
        #will automatically thaw here

    """
    def __init__(self, ctrl):
        self.ctrl = ctrl
    def __enter__(self):#started the with... statement
        if sys.platform!='darwin':#this is only tested on OSX
            return self.ctrl
        if self.ctrl is not None:#check it hasn't been deleted
            self.ctrl.Freeze()
        return self.ctrl
    def __exit__(self, exc_type, exc_val, exc_tb):#ended the with... statement
        if sys.platform!='darwin':#this is only tested on OSX
            return
        if self.ctrl is not None:#check it hasn't been deleted
            self.ctrl.Thaw()
class FlowPanel(wx.ScrolledWindow):
    def __init__(self, frame, id=-1):
        """A panel that shows how the routines will fit together
        """
        self.frame=frame
        self.app=frame.app
        self.dpi=self.app.dpi
        wx.ScrolledWindow.__init__(self, frame, id, (0, 0),size = wx.Size(8*self.dpi,3*self.dpi), style=wx.HSCROLL|wx.VSCROLL)
        self.SetBackgroundColour(canvasColor)
        self.needUpdate=True
        self.maxWidth  = 50*self.dpi
        self.maxHeight = 2*self.dpi
        self.mousePos = None
        #if we're adding a loop or routine then add spots to timeline
        #self.drawNearestRoutinePoint = True
        #self.drawNearestLoopPoint = False
        self.pointsToDraw=[] #lists the x-vals of points to draw, eg loop locations
        self.appData = self.app.prefs.appData # for flowSize, showLoopInfoInFlow

        #self.SetAutoLayout(True)
        self.SetScrollRate(self.dpi/4,self.dpi/4)

        # create a PseudoDC to record our drawing
        self.pdc = wx.PseudoDC()
        self.pen_cache = {}
        self.brush_cache = {}
        # vars for handling mouse clicks
        self.hitradius=5
        self.dragid = -1
        self.entryPointPosList = []
        self.entryPointIDlist = []
        self.mode = 'normal'#can also be 'loopPoint1','loopPoint2','routinePoint'
        self.insertingRoutine=""

        #for the context menu
        self.componentFromID={}#use the ID of the drawn icon to retrieve component (loop or routine)
        self.contextMenuItems=['remove']
        self.contextItemFromID={}; self.contextIDFromItem={}
        for item in self.contextMenuItems:
            id = wx.NewId()
            self.contextItemFromID[id] = item
            self.contextIDFromItem[item] = id

        #self.btnInsertRoutine = wx.Button(self,-1,'Insert Routine', pos=(10,10))
        #self.btnInsertLoop = wx.Button(self,-1,'Insert Loop', pos=(10,30))
        self.btnInsertRoutine = platebtn.PlateButton(self,-1,'Insert Routine ', pos=(10,10))
        self.btnInsertLoop = platebtn.PlateButton(self,-1,'Insert Loop     ', pos=(10,30)) #spaces give size for CANCEL

        self.labelTextGray = {'normal': wx.Color(150,150,150, 20),'hlight':wx.Color(150,150,150, 20)}
        self.labelTextRed = {'normal': wx.Color(250,10,10, 250),'hlight':wx.Color(250,10,10, 250)}
        self.labelTextBlack = {'normal': wx.Color(0,0,0, 250),'hlight':wx.Color(250,250,250, 250)}

        # use self.appData['flowSize'] to index a tuple to get a specific value, eg: (4,6,8)[self.appData['flowSize']]
        self.flowMaxSize = 2 # upper limit on increaseSize

        if self.app.prefs.app['debugMode']:
            self.btnViewNamespace = platebtn.PlateButton(self,-1,'namespace', pos=(10,70))
            self.btnViewNamespace.SetLabelColor(**self.labelTextGray)

        self.draw()

        #bind events
        self.Bind(wx.EVT_MOUSE_EVENTS, self.OnMouse)
        self.Bind(wx.EVT_BUTTON, self.onInsertRoutine,self.btnInsertRoutine)
        self.Bind(wx.EVT_BUTTON, self.setLoopPoint1,self.btnInsertLoop)
        if self.app.prefs.app['debugMode']:
            self.Bind(wx.EVT_BUTTON, self.dumpNamespace, self.btnViewNamespace)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.SetDropTarget(FileDropTarget(builder = self.frame))

        idClear = wx.NewId()
        self.Bind(wx.EVT_MENU, self.clearMode, id=idClear )
        aTable = wx.AcceleratorTable([
                              (wx.ACCEL_NORMAL, wx.WXK_ESCAPE, idClear)
                              ])
        self.SetAcceleratorTable(aTable)
    def clearMode(self, event=None):
        """If we were in middle of doing something (like inserting routine) then
        end it, allowing user to cancel
        """
        self.mode='normal'
        self.insertingRoutine=None
        for id in self.entryPointIDlist:
            self.pdc.RemoveId(id)
        self.entryPointPosList = []
        self.entryPointIDlist = []
        self.draw()
        self.frame.SetStatusText("")
        self.btnInsertRoutine.SetLabel('Insert Routine')
        self.btnInsertRoutine.SetLabelColor(**self.labelTextBlack)
        self.btnInsertLoop.SetLabel('Insert Loop')
        self.btnInsertLoop.SetLabelColor(**self.labelTextBlack)
    def ConvertEventCoords(self, event):
        xView, yView = self.GetViewStart()
        xDelta, yDelta = self.GetScrollPixelsPerUnit()
        return (event.GetX() + (xView * xDelta),
            event.GetY() + (yView * yDelta))

    def OffsetRect(self, r):
        """Offset the rectangle, r, to appear in the given position in the window
        """
        xView, yView = self.GetViewStart()
        xDelta, yDelta = self.GetScrollPixelsPerUnit()
        r.OffsetXY(-(xView*xDelta),-(yView*yDelta))

    def onInsertRoutine(self, evt):
        """For when the insert Routine button is pressed - bring up dialog and
        present insertion point on flow line.
        see self.insertRoutine() for further info
        """
        if self.mode.startswith('loopPoint'):
            self.clearMode()
        elif self.mode == 'routine': # clicked again with label now being "Cancel..."
            self.clearMode()
            return
        self.frame.SetStatusText("Select a Routine to insert (Esc to exit)")
        menu = wx.Menu()
        self.routinesFromID={}
        id = wx.NewId()
        menu.Append(id, '(new)')
        self.routinesFromID[id] = '(new)'
        wx.EVT_MENU(menu, id, self.insertNewRoutine)
        for routine in self.frame.exp.routines:
            id = wx.NewId()
            menu.Append( id, routine )
            self.routinesFromID[id]=routine
            wx.EVT_MENU( menu, id, self.onInsertRoutineSelect )
        btnPos = self.btnInsertRoutine.GetRect()
        menuPos = (btnPos[0], btnPos[1]+btnPos[3])
        self.PopupMenu( menu, menuPos )
        menu.Bind(wx.EVT_MENU_CLOSE, self.clearMode)
        menu.Destroy() # destroy to avoid mem leak
    def insertNewRoutine(self, event):
        """selecting (new) is a short-cut for: make new routine, insert it into the flow
        """
        newRoutine = self.frame.routinePanel.createNewRoutine(returnName=True)
        if newRoutine:
            self.routinesFromID[event.GetId()] = newRoutine
            self.onInsertRoutineSelect(event)
        else:
            self.clearMode()
    def onInsertRoutineSelect(self,event):
        """User has selected a routine to be entered so bring up the entrypoint marker
        and await mouse button press.
        see self.insertRoutine() for further info
        """
        self.mode='routine'
        self.btnInsertRoutine.SetLabel('CANCEL Insert')
        self.btnInsertRoutine.SetLabelColor(**self.labelTextRed)
        self.frame.SetStatusText('Click where you want to insert the Routine, or CANCEL insert.')
        self.insertingRoutine = self.routinesFromID[event.GetId()]
        x = self.getNearestGapPoint(0)
        self.drawEntryPoints([x])
    def insertRoutine(self, ii):
        """Insert a routine into the Flow having determined its name and location

        onInsertRoutine() the button has been pressed so present menu
        onInsertRoutineSelect() user selected the name so present entry points
        OnMouse() user has selected a point on the timeline to insert entry

        """
        self.frame.exp.flow.addRoutine(self.frame.exp.routines[self.insertingRoutine], ii)
        self.frame.addToUndoStack("AddRoutine")
        #reset flow drawing (remove entry point)
        self.clearMode()

    def setLoopPoint1(self, evt=None):
        """Someone pushed the insert loop button.
        Fetch the dialog
        """
        if self.mode == 'routine':
            self.clearMode()
        elif self.mode.startswith('loopPoint'): # clicked again, label is "Cancel..."
            self.clearMode()
            return
        self.btnInsertLoop.SetLabel('CANCEL insert')
        self.btnInsertLoop.SetLabelColor(**self.labelTextRed)
        self.mode='loopPoint1'
        self.frame.SetStatusText('Click where you want the loop to start/end, or CANCEL insert.')
        x = self.getNearestGapPoint(0)
        self.drawEntryPoints([x])
    def setLoopPoint2(self, evt=None):
        """Someone pushed the insert loop button.
        Fetch the dialog
        """
        self.mode='loopPoint2'
        self.frame.SetStatusText('Click the other start/end for the loop')
        x = self.getNearestGapPoint(wx.GetMousePosition()[0]-self.GetScreenPosition()[0],
            exclude=[self.entryPointPosList[0]])#exclude point 1
        self.drawEntryPoints([self.entryPointPosList[0], x])

    def insertLoop(self, evt=None):
        #bring up listbox to choose the routine to add and/or create a new one
        loopDlg = DlgLoopProperties(frame=self.frame,
            helpUrl = self.app.urls['builder.loops'])
        startII = self.gapMidPoints.index(min(self.entryPointPosList))
        endII = self.gapMidPoints.index(max(self.entryPointPosList))
        if loopDlg.OK:
            handler=loopDlg.currentHandler
            self.frame.exp.flow.addLoop(handler,
                startPos=startII, endPos=endII)
            self.frame.addToUndoStack("AddLoopToFlow")
        self.clearMode()
        self.draw()
    def dumpNamespace(self, evt=None):
        nsu = self.frame.exp.namespace.user
        if len(nsu) == 0:
            print "______________________\n <namespace is empty>"
            return
        nsu.sort()
        m = min(20, 2 + max([len(n) for n in nsu]))  # 2+len of longest word, or 20
        fmt = "%-"+str(m)+"s"  # format string: each word padded to longest
        nsu = map(lambda x: fmt % x, nsu)
        c = min(6, max(2, len(nsu)//4))  # number of columns, 2 - 6
        while len(nsu) % c: nsu += [' '] # avoid index errors later
        r = len(nsu) // c  # number of rows
        print '_' * c * m
        for i in range(r):
            print ' '+''.join([nsu[i+j*r] for j in range(c)])  # typially to coder output
        collisions = self.frame.exp.namespace.getCollisions()
        if collisions:
            print "*** collisions ***: %s" % str(collisions)
    def increaseSize(self, event=None):
        if self.appData['flowSize'] == self.flowMaxSize:
            self.appData['showLoopInfoInFlow'] = True
        self.appData['flowSize'] = min(self.flowMaxSize, self.appData['flowSize'] + 1)
        self.clearMode() #redraws
    def decreaseSize(self, event=None):
        if self.appData['flowSize'] == 0:
            self.appData['showLoopInfoInFlow'] = False
        self.appData['flowSize'] = max(0, self.appData['flowSize'] - 1)
        self.clearMode() # redraws
    def editLoopProperties(self, event=None, loop=None):
        if event:#we got here from a wx.button press (rather than our own drawn icons)
            loopName=event.EventObject.GetName()
            loop=self.routine.getLoopFromName(loopName)

        #add routine points to the timeline
        self.setDrawPoints('loops')
        self.draw()
        if 'conditions' in loop.params.keys():
            condOrig = loop.params['conditions'].val
            condFileOrig = loop.params['conditionsFile'].val
        loopDlg = DlgLoopProperties(frame=self.frame,
            helpUrl = self.app.urls['builder.loops'],
            title=loop.params['name'].val+' Properties', loop=loop)
        if loopDlg.OK:
            prevLoop=loop
            if loopDlg.params['loopType'].val=='staircase':
                loop= loopDlg.stairHandler
            elif loopDlg.params['loopType'].val=='interleaved stairs':
                loop= loopDlg.multiStairHandler
            else:
                loop=loopDlg.trialHandler #['random','sequential', 'fullRandom', ]
            #if the loop is a whole new class then we can't just update the params
            if loop.getType()!=prevLoop.getType():
                #get indices for start and stop points of prev loop
                flow = self.frame.exp.flow
                startII = flow.index(prevLoop.initiator)#find the index of the initator
                endII = flow.index(prevLoop.terminator)-1 #minus one because initator will have been deleted
                #remove old loop completely
                flow.removeComponent(prevLoop)
                #finally insert the new loop
                flow.addLoop(loop, startII, endII)
            self.frame.addToUndoStack("Edit Loop")
        elif 'conditions' in loop.params.keys():
            loop.params['conditions'].val = condOrig
            loop.params['conditionsFile'].val = condFileOrig
        #remove the points from the timeline
        self.setDrawPoints(None)
        self.draw()

    def OnMouse(self, event):
        x,y = self.ConvertEventCoords(event)
        if self.mode=='normal':
            if event.LeftDown():
                icons = self.pdc.FindObjectsByBBox(x, y)
                for thisIcon in icons:#might intersect several and only one has a callback
                    if thisIcon in self.componentFromID:
                        comp=self.componentFromID[thisIcon]
                        if comp.getType() in ['StairHandler', 'TrialHandler', 'MultiStairHandler']:
                            self.editLoopProperties(loop=comp)
                        if comp.getType() == 'Routine':
                            self.frame.routinePanel.setCurrentRoutine(routine=comp)
            elif event.RightDown():
                icons = self.pdc.FindObjectsByBBox(x, y)
                comp=None
                for thisIcon in icons:#might intersect several and only one has a callback
                    if thisIcon in self.componentFromID:
                        #loop through comps looking for Routine, or a Loop if no routine
                        thisComp=self.componentFromID[thisIcon]
                        if thisComp.getType() in ['StairHandler', 'TrialHandler', 'MultiStairHandler']:
                            comp=thisComp#use this if we don't find a routine
                            icon=thisIcon
                        if thisComp.getType() == 'Routine':
                            comp=thisComp
                            icon=thisIcon
                            break#we've found a Routine so stop looking
                try:
                    self._menuComponentID=icon
                    self.showContextMenu(self._menuComponentID,
                        xy=wx.Point(x+self.GetPosition()[0],y+self.GetPosition()[1]))
                except UnboundLocalError:
                    # right click but not on an icon
                    self.Refresh() # might as well do something
        elif self.mode=='routine':
            if event.LeftDown():
                self.insertRoutine(ii=self.gapMidPoints.index(self.entryPointPosList[0]))
            else:#move spot if needed
                point = self.getNearestGapPoint(mouseX=x)
                self.drawEntryPoints([point])
        elif self.mode=='loopPoint1':
            if event.LeftDown():
                self.setLoopPoint2()
            else:#move spot if needed
                point = self.getNearestGapPoint(mouseX=x)
                self.drawEntryPoints([point])
        elif self.mode=='loopPoint2':
            if event.LeftDown():
                self.insertLoop()
            else:#move spot if needed
                point = self.getNearestGapPoint(mouseX=x)
                self.drawEntryPoints([self.entryPointPosList[0], point])
    def getNearestGapPoint(self, mouseX, exclude=[]):
        d=1000000000
        nearest=None
        for point in self.gapMidPoints:
            if point in exclude: continue
            if (point-mouseX)**2 < d:
                d=(point-mouseX)**2
                nearest=point
        return nearest
    def showContextMenu(self, component, xy):
        menu = wx.Menu()
        for item in self.contextMenuItems:
            id = self.contextIDFromItem[item]
            menu.Append( id, item )
            wx.EVT_MENU( menu, id, self.onContextSelect )
        self.frame.PopupMenu( menu, xy )
        menu.Destroy() # destroy to avoid mem leak
    def onContextSelect(self, event):
        """Perform a given action on the component chosen
        """
        op = self.contextItemFromID[event.GetId()]
        component=self.componentFromID[self._menuComponentID]
        flow = self.frame.exp.flow
        if op=='remove':
            # remove name from namespace only if its a loop (which exists only in the flow)
            if 'conditionsFile' in component.params.keys():
                conditionsFile = component.params['conditionsFile'].val
                if conditionsFile and conditionsFile not in ['None','']:
                    _, fieldNames = data.importConditions(conditionsFile, returnFieldNames=True)
                    for fname in fieldNames:
                        self.frame.exp.namespace.remove(fname)
                self.frame.exp.namespace.remove(component.params['name'].val)
            flow.removeComponent(component, id=self._menuComponentID)
            self.frame.addToUndoStack("removed %s from flow" %component.params['name'])
        if op=='rename':
            print 'rename is not implemented yet'
            #if component is a loop: DlgLoopProperties
            #elif comonent is a routine: DlgRoutineProperties
        self.draw()
        self._menuComponentID=None

    def OnPaint(self, event):
        # Create a buffered paint DC.  It will create the real
        # wx.PaintDC and then blit the bitmap to it when dc is
        # deleted.
        dc = wx.BufferedPaintDC(self)
        dc = wx.GCDC(dc)
        # use PrepateDC to set position correctly
        self.PrepareDC(dc)
        # we need to clear the dc BEFORE calling PrepareDC
        bg = wx.Brush(self.GetBackgroundColour())
        dc.SetBackground(bg)
        dc.Clear()
        # create a clipping rect from our position and size
        # and the Update Region
        xv, yv = self.GetViewStart()
        dx, dy = self.GetScrollPixelsPerUnit()
        x, y   = (xv * dx, yv * dy)
        rgn = self.GetUpdateRegion()
        rgn.Offset(x,y)
        r = rgn.GetBox()
        # draw to the dc using the calculated clipping rect
        self.pdc.DrawToDCClipped(dc,r)

    def draw(self, evt=None):
        """This is the main function for drawing the Flow panel.
        It should be called whenever something changes in the exp.

        This then makes calls to other drawing functions, like drawEntryPoints...
        """
        if not hasattr(self.frame, 'exp'):
            return#we haven't yet added an exp
        expFlow = self.frame.exp.flow #retrieve the current flow from the experiment
        pdc=self.pdc

        self.componentFromID={}#use the ID of the drawn icon to retrieve component (loop or routine)

        pdc.Clear()#clear the screen
        pdc.RemoveAll()#clear all objects (icon buttons)
        pdc.BeginDrawing()

        font = self.GetFont()

        #draw the main time line
        self.linePos = (2.5*self.dpi,0.5*self.dpi) #x,y of start
        gap = self.dpi / (6, 4, 2) [self.appData['flowSize']]
        dLoopToBaseLine = (15, 25, 43) [self.appData['flowSize']]
        dBetweenLoops = (20, 24, 30) [self.appData['flowSize']]

        #guess virtual size; nRoutines wide by nLoops high
        #make bigger than needed and shrink later
        nRoutines = len(expFlow)
        nLoops = 0
        for entry in expFlow:
            if entry.getType()=='LoopInitiator': nLoops+=1
        self.SetVirtualSize(size=(nRoutines*self.dpi*2, nLoops*dBetweenLoops+dLoopToBaseLine*3))

        #step through components in flow, get spacing info from text size, etc
        currX=self.linePos[0]
        lineId=wx.NewId()
        pdc.DrawLine(x1=self.linePos[0]-gap,y1=self.linePos[1],x2=self.linePos[0],y2=self.linePos[1])
        self.loops={}#NB the loop is itself the key!? and the value is further info about it
        nestLevel=0; maxNestLevel=0
        self.gapMidPoints=[currX-gap/2]
        for ii, entry in enumerate(expFlow):
            if entry.getType()=='LoopInitiator':
                self.loops[entry.loop]={'init':currX,'nest':nestLevel, 'id':ii}#NB the loop is itself the dict key!?
                nestLevel+=1#start of loop so increment level of nesting
                maxNestLevel = max(nestLevel, maxNestLevel)
            elif entry.getType()=='LoopTerminator':
                self.loops[entry.loop]['term']=currX #NB the loop is itself the dict key!
                nestLevel-=1#end of loop so decrement level of nesting
            elif entry.getType()=='Routine':
                # just get currX based on text size, don't draw anything yet:
                currX = self.drawFlowRoutine(pdc,entry, id=ii,pos=[currX,self.linePos[1]-10], draw=False)
            self.gapMidPoints.append(currX+gap/2)
            pdc.SetId(lineId)
            pdc.SetPen(wx.Pen(wx.Color(0,0,0, 255)))
            pdc.DrawLine(x1=currX,y1=self.linePos[1],x2=currX+gap,y2=self.linePos[1])
            currX+=gap
        lineRect = wx.Rect(self.linePos[0]-2, self.linePos[1]-2, currX-self.linePos[0]+2, 4)
        pdc.SetIdBounds(lineId,lineRect)

        # draw the loops first:
        maxHeight = 0
        for thisLoop in self.loops:
            thisInit = self.loops[thisLoop]['init']
            thisTerm = self.loops[thisLoop]['term']
            thisNest = maxNestLevel-self.loops[thisLoop]['nest']-1
            thisId = self.loops[thisLoop]['id']
            height = self.linePos[1]+dLoopToBaseLine + thisNest*dBetweenLoops
            self.drawLoop(pdc,thisLoop,id=thisId,
                        startX=thisInit, endX=thisTerm,
                        base=self.linePos[1],height=height)
            self.drawLoopStart(pdc,pos=[thisInit,self.linePos[1]])
            self.drawLoopEnd(pdc,pos=[thisTerm,self.linePos[1]])
            if height>maxHeight: maxHeight=height

        # draw routines second (over loop lines):
        currX=self.linePos[0]
        for ii, entry in enumerate(expFlow):
            if entry.getType()=='Routine':
                currX = self.drawFlowRoutine(pdc,entry, id=ii,pos=[currX,self.linePos[1]-10])
            pdc.SetPen(wx.Pen(wx.Color(0,0,0, 255)))
            pdc.DrawLine(x1=currX,y1=self.linePos[1],x2=currX+gap,y2=self.linePos[1])
            currX += gap

        self.SetVirtualSize(size=(currX+100, maxHeight+50))

        #draw all possible locations for routines DEPRECATED SINCE 1.62 because not drawing those
        #for n, xPos in enumerate(self.pointsToDraw):
        #   font.SetPointSize(600/self.dpi)
        #   self.SetFont(font); pdc.SetFont(font)
        #   w,h = self.GetFullTextExtent(str(len(self.pointsToDraw)))[0:2]
        #   pdc.SetPen(wx.Pen(wx.Color(0,0,0, 255)))
        #   pdc.SetBrush(wx.Brush(wx.Color(0,0,0,255)))
        #   pdc.DrawCircle(xPos,self.linePos[1], w+2)
        #   pdc.SetTextForeground([255,255,255])
        #   pdc.DrawText(str(n), xPos-w/2, self.linePos[1]-h/2)

        self.drawLineStart(pdc, (self.linePos[0]-gap,self.linePos[1]))
        self.drawLineEnd(pdc, (currX, self.linePos[1]))

        pdc.EndDrawing()
        self.Refresh()#refresh the visible window after drawing (using OnPaint)
    def drawEntryPoints(self, posList):
        ptSize = (3,4,5)[self.appData['flowSize']]
        for n, pos in enumerate(posList):
            if n>=len(self.entryPointPosList):
                #draw for first time
                id = wx.NewId()
                self.entryPointIDlist.append(id)
                self.pdc.SetId(id)
                self.pdc.SetBrush(wx.Brush(wx.Color(0,0,0,255)))
                self.pdc.DrawCircle(pos,self.linePos[1], ptSize)
                r = self.pdc.GetIdBounds(id)
                self.OffsetRect(r)
                self.RefreshRect(r, False)
            elif pos == self.entryPointPosList[n]:
                pass#nothing to see here, move along please :-)
            else:
                #move to new position
                dx = pos-self.entryPointPosList[n]
                dy = 0
                r = self.pdc.GetIdBounds(self.entryPointIDlist[n])
                self.pdc.TranslateId(self.entryPointIDlist[n], dx, dy)
                r2 = self.pdc.GetIdBounds(self.entryPointIDlist[n])
                rectToRedraw = r.Union(r2)#combine old and new locations to get redraw area
                rectToRedraw.Inflate(4,4)
                self.OffsetRect(rectToRedraw)
                self.RefreshRect(rectToRedraw, False)

        self.entryPointPosList=posList
        self.Refresh()#refresh the visible window after drawing (using OnPaint)

    def setDrawPoints(self, ptType, startPoint=None):
        """Set the points of 'routines', 'loops', or None
        """
        if ptType=='routines':
            self.pointsToDraw=self.gapMidPoints
        elif ptType=='loops':
            self.pointsToDraw=self.gapMidPoints
        else:
            self.pointsToDraw=[]
    def drawLineStart(self, dc, pos):
        #draw bar at start of timeline; circle looked bad, offset vertically
        ptSize = (3,3,4)[self.appData['flowSize']]
        dc.SetBrush(wx.Brush(wx.Color(0,0,0, 255)))
        dc.SetPen(wx.Pen(wx.Color(0,0,0, 255)))
        dc.DrawPolygon([[0,-ptSize],[1,-ptSize],[1,ptSize], [0,ptSize]], pos[0],pos[1])
    def drawLineEnd(self, dc, pos):
        #draws arrow at end of timeline
        #tmpId = wx.NewId()
        #dc.SetId(tmpId)
        dc.SetBrush(wx.Brush(wx.Color(0,0,0, 255)))
        dc.SetPen(wx.Pen(wx.Color(0,0,0, 255)))
        dc.DrawPolygon([[0,-3],[5,0],[0,3]], pos[0],pos[1])
        #dc.SetIdBounds(tmpId,wx.Rect(pos[0],pos[1]+3,5,6))
    def drawLoopEnd(self, dc, pos, downwards=True):
        # define the right side of a loop but draw nothing
        # idea: might want a wxID for grabbing and relocating the loop endpoint
        tmpId = wx.NewId()
        dc.SetId(tmpId)
        #dc.SetBrush(wx.Brush(wx.Color(0,0,0, 250)))
        #dc.SetPen(wx.Pen(wx.Color(0,0,0, 255)))
        size = (3,4,5)[self.appData['flowSize']]
        #if downwards: dc.DrawPolygon([[size,0],[0,size],[-size,0]], pos[0],pos[1]+2*size)#points down
        #else: dc.DrawPolygon([[size,size],[0,0],[-size,size]], pos[0],pos[1]-3*size)#points up
        dc.SetIdBounds(tmpId,wx.Rect(pos[0]-size,pos[1]-size,2*size,2*size))
        return
    def drawLoopStart(self, dc, pos, downwards=True):
        # draws direction arrow on left side of a loop
        tmpId = wx.NewId()
        dc.SetId(tmpId)
        dc.SetBrush(wx.Brush(wx.Color(0,0,0, 250)))
        dc.SetPen(wx.Pen(wx.Color(0,0,0, 255)))
        size = (3,4,5)[self.appData['flowSize']]
        offset = (3,2,0)[self.appData['flowSize']]
        if downwards:
            dc.DrawPolygon([[size,size],[0,0],[-size,size]], pos[0],pos[1]+3*size-offset)#points up
        else:
            dc.DrawPolygon([[size,0],[0,size],[-size,0]], pos[0],pos[1]-4*size)#points down
        dc.SetIdBounds(tmpId,wx.Rect(pos[0]-size,pos[1]-size,2*size,2*size))
    def drawFlowRoutine(self,dc,routine,id, rgb=[200,50,50],pos=[0,0], draw=True):
        """Draw a box to show a routine on the timeline
        draw=False is for a dry-run, esp to compute and return size information without drawing or setting a pdc ID
        """
        name = routine.name
        if self.appData['flowSize']==0 and len(name) > 5:
            name = ' '+name[:4]+'..'
        else:
            name = ' '+name+' '
        if draw:
            dc.SetId(id)
        font = self.GetFont()
        if sys.platform=='darwin':
            fontSizeDelta = (9,6,0)[self.appData['flowSize']]
            font.SetPointSize(1400/self.dpi-fontSizeDelta)
        elif sys.platform.startswith('linux'):
            fontSizeDelta = (6,4,0)[self.appData['flowSize']]
            font.SetPointSize(1400/self.dpi-fontSizeDelta)
        else:
            fontSizeDelta = (8,4,0)[self.appData['flowSize']]
            font.SetPointSize(1000/self.dpi-fontSizeDelta)
        r, g, b = rgb

        #get size based on text
        self.SetFont(font)
        if draw: dc.SetFont(font)
        w,h = self.GetFullTextExtent(name)[0:2]
        pad = (5,10,20)[self.appData['flowSize']]
        #draw box
        pos[1] += 2-self.appData['flowSize']
        rect = wx.Rect(pos[0], pos[1], w+pad,h+pad)
        endX = pos[0]+w+pad
        #the edge should match the text
        if draw:
            dc.SetPen(wx.Pen(wx.Color(r, g, b, wx.ALPHA_OPAQUE)))
            #for the fill, draw once in white near-opaque, then in transp color
            dc.SetBrush(wx.Brush(routineFlowColor))
            dc.DrawRoundedRectangleRect(rect, (4,6,8)[self.appData['flowSize']])
            #draw text
            dc.SetTextForeground(rgb)
            dc.DrawText(name, pos[0]+pad/2, pos[1]+pad/2)

            self.componentFromID[id]=routine
            #set the area for this component
            dc.SetIdBounds(id,rect)

        return endX

        #tbtn = AB.AquaButton(self, id, pos=pos, label=name)
        #tbtn.Bind(wx.EVT_BUTTON, self.onBtn)
        #print tbtn.GetBackgroundColour()

        #print dir(tbtn)
        #print tbtn.GetRect()
        #rect = tbtn.GetRect()
        #return rect[0]+rect[2]+20
    #def onBtn(self, event):
        #print 'evt:', self.componentFromID[event.GetId()].name
        #print '\nobj:', dir(event.GetEventObject())
    def drawLoop(self,dc,loop,id, startX,endX,
            base,height,rgb=[0,0,0], downwards=True):
        if downwards: up=-1
        else: up=+1

        #draw loop itself, as transparent rect with curved corners
        tmpId = wx.NewId()
        dc.SetId(tmpId)
        curve = (6, 11, 15)[self.appData['flowSize']] #extra distance, in both h and w for curve
        yy = [base,height+curve*up,height+curve*up/2,height] # for area
        r,g,b=rgb
        dc.SetPen(wx.Pen(wx.Color(r, g, b, 200)))
        vertOffset=0 # 1 is interesting too
        area = wx.Rect(startX, base+vertOffset, endX-startX, max(yy)-min(yy))
        dc.SetBrush(wx.Brush(wx.Color(0,0,0,0),style=wx.TRANSPARENT)) # transparent
        dc.DrawRoundedRectangleRect(area, curve) # draws outline
        dc.SetIdBounds(tmpId, area)

        #add a name label, loop info, except at smallest size
        name = loop.params['name'].val
        if self.appData['showLoopInfoInFlow'] and not self.appData['flowSize']==0:
            if 'conditions' in loop.params.keys() and loop.params['conditions'].val:
                xnumTrials = 'x'+str(len(loop.params['conditions'].val))
            else: xnumTrials = ''
            name += '  ('+str(loop.params['nReps'].val)+xnumTrials
            abbrev = ['', {'random': 'rand.', 'sequential': 'sequ.', 'fullRandom':'f-ran.',
                      'staircase': 'stair.', 'interleaved staircases': "int-str."},
                      {'random': 'random', 'sequential': 'sequential', 'fullRandom':'fullRandom',
                      'staircase': 'staircase', 'interleaved staircases': "interl'vd stairs"}]
            name += ' '+abbrev[self.appData['flowSize']][loop.params['loopType'].val]+')'
        if self.appData['flowSize']==0:
            if len(name) > 9:
                name = ' '+name[:8]+'..'
            else: name = ' '+name[:9]
        else:
            name = ' '+name+' '

        dc.SetId(id)
        font = self.GetFont()
        if sys.platform=='darwin':
            basePtSize = (650,750,900)[self.appData['flowSize']]
        elif sys.platform.startswith('linux'):
            basePtSize = (750,850,1000)[self.appData['flowSize']]
        else:
            basePtSize = (700,750,800)[self.appData['flowSize']]
        font.SetPointSize(basePtSize/self.dpi)
        self.SetFont(font)
        dc.SetFont(font)

        #get size based on text
        pad = (5,8,10)[self.appData['flowSize']]
        w,h = self.GetFullTextExtent(name)[0:2]
        x = startX+(endX-startX)/2-w/2-pad/2
        y = (height-h/2)

        #draw box
        rect = wx.Rect(x, y, w+pad,h+pad)
        #the edge should match the text
        dc.SetPen(wx.Pen(wx.Color(r, g, b, 100)))
        #try to make the loop fill brighter than the background canvas:
        dc.SetBrush(wx.Brush(wx.Color(235,235,235, 250)))

        dc.DrawRoundedRectangleRect(rect, (4,6,8)[self.appData['flowSize']])
        #draw text
        dc.SetTextForeground([r,g,b])
        dc.DrawText(name, x+pad/2, y+pad/2)

        self.componentFromID[id]=loop
        #set the area for this component
        dc.SetIdBounds(id,rect)

class RoutineCanvas(wx.ScrolledWindow):
    """Represents a single routine (used as page in RoutinesNotebook)"""
    def __init__(self, notebook, id=-1, routine=None):
        """This window is based heavily on the PseudoDC demo of wxPython
        """
        wx.ScrolledWindow.__init__(self, notebook, id, (0, 0), style=wx.SUNKEN_BORDER)

        self.SetBackgroundColour(canvasColor)
        self.notebook=notebook
        self.frame=notebook.frame
        self.app=self.frame.app
        self.dpi=self.app.dpi
        self.lines = []
        self.maxWidth  = 15*self.dpi
        self.maxHeight = 15*self.dpi
        self.x = self.y = 0
        self.curLine = []
        self.drawing = False
        self.drawSize = self.app.prefs.appData['routineSize']
        # auto-rescale based on number of components and window size looks jumpy
        # when switch between routines of diff drawing sizes
        self.iconSize = (24,24,48)[self.drawSize] # only 24, 48 so far
        self.fontBaseSize = (800,900,1000)[self.drawSize] # depends on OS?

        self.SetVirtualSize((self.maxWidth, self.maxHeight))
        self.SetScrollRate(self.dpi/4,self.dpi/4)

        self.routine=routine
        self.yPositions=None
        self.yPosTop=(25,40,60)[self.drawSize]
        self.componentStep=(25,32,50)[self.drawSize]#the step in Y between each component
        self.timeXposStart = (150,150,200)[self.drawSize]
        self.iconXpos = self.timeXposStart - self.iconSize*(1.3,1.5,1.5)[self.drawSize] #the left hand edge of the icons
        self.timeXposEnd = self.timeXposStart + 400 # onResize() overrides

        # create a PseudoDC to record our drawing
        self.pdc = wx.PseudoDC()
        self.pen_cache = {}
        self.brush_cache = {}
        # vars for handling mouse clicks
        self.dragid = -1
        self.lastpos = (0,0)
        self.componentFromID={}#use the ID of the drawn icon to retrieve component name
        self.contextMenuItems=['edit','remove','move to top','move up','move down','move to bottom']
        self.contextItemFromID={}; self.contextIDFromItem={}
        for item in self.contextMenuItems:
            id = wx.NewId()
            self.contextItemFromID[id] = item
            self.contextIDFromItem[item] = id

        self.redrawRoutine()

        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda x:None)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.OnMouse)
        self.Bind(wx.EVT_SIZE, self.onResize)
        #self.SetDropTarget(FileDropTarget(builder = self.frame)) # crashes if drop on OSX

    def onResize(self, event):
        self.sizePix=event.GetSize()
        self.timeXposStart = (150,150,200)[self.drawSize]
        self.timeXposEnd = self.sizePix[0]-(60,80,100)[self.drawSize]
        self.redrawRoutine()#then redraw visible
    def ConvertEventCoords(self, event):
        xView, yView = self.GetViewStart()
        xDelta, yDelta = self.GetScrollPixelsPerUnit()
        return (event.GetX() + (xView * xDelta),
            event.GetY() + (yView * yDelta))
    def OffsetRect(self, r):
        """Offset the rectangle, r, to appear in the given position in the window
        """
        xView, yView = self.GetViewStart()
        xDelta, yDelta = self.GetScrollPixelsPerUnit()
        r.OffsetXY(-(xView*xDelta),-(yView*yDelta))

    def OnMouse(self, event):
        if event.LeftDown():
            x,y = self.ConvertEventCoords(event)
            icons = self.pdc.FindObjectsByBBox(x, y)
            if len(icons):
                self.editComponentProperties(component=self.componentFromID[icons[0]])
        elif event.RightDown():
            x,y = self.ConvertEventCoords(event)
            icons = self.pdc.FindObjectsByBBox(x, y)
            if len(icons):
                self._menuComponent=self.componentFromID[icons[0]]
                self.showContextMenu(self._menuComponent, xy=event.GetPosition())
        elif event.Dragging() or event.LeftUp():
            if self.dragid != -1:
                pass
            if event.LeftUp():
                pass
    def showContextMenu(self, component, xy):
        menu = wx.Menu()
        for item in self.contextMenuItems:
            id = self.contextIDFromItem[item]
            menu.Append( id, item )
            wx.EVT_MENU( menu, id, self.onContextSelect )
        self.frame.PopupMenu( menu, xy )
        menu.Destroy() # destroy to avoid mem leak

    def onContextSelect(self, event):
        """Perform a given action on the component chosen
        """
        op = self.contextItemFromID[event.GetId()]
        component=self._menuComponent
        r = self.routine
        if op=='edit':
            self.editComponentProperties(component=component)
        elif op=='remove':
            r.remove(component)
            self.frame.addToUndoStack("removed" + component.params['name'].val)
            self.frame.exp.namespace.remove(component.params['name'].val)
        elif op.startswith('move'):
            lastLoc=r.index(component)
            r.remove(component)
            if op=='move to top': r.insert(0, component)
            if op=='move up': r.insert(lastLoc-1, component)
            if op=='move down': r.insert(lastLoc+1, component)
            if op=='move to bottom': r.append(component)
            self.frame.addToUndoStack("moved" + component.params['name'].val)
        self.redrawRoutine()
        self._menuComponent=None
    def OnPaint(self, event):
        # Create a buffered paint DC.  It will create the real
        # wx.PaintDC and then blit the bitmap to it when dc is
        # deleted.
        dc = wx.BufferedPaintDC(self)
        if sys.platform.startswith('linux'):
            gcdc = dc
        else:
            gcdc = wx.GCDC(dc)
        # use PrepateDC to set position correctly
        self.PrepareDC(dc)
        # we need to clear the dc BEFORE calling PrepareDC
        bg = wx.Brush(self.GetBackgroundColour())
        gcdc.SetBackground(bg)
        gcdc.Clear()
        # create a clipping rect from our position and size
        # and the Update Region
        xv, yv = self.GetViewStart()
        dx, dy = self.GetScrollPixelsPerUnit()
        x, y   = (xv * dx, yv * dy)
        rgn = self.GetUpdateRegion()
        rgn.Offset(x,y)
        r = rgn.GetBox()
        # draw to the dc using the calculated clipping rect
        self.pdc.DrawToDCClipped(gcdc,r)

    def redrawRoutine(self):
        self.pdc.Clear()#clear the screen
        self.pdc.RemoveAll()#clear all objects (icon buttons)

        self.pdc.BeginDrawing()

        #work out where the component names and icons should be from name lengths
        self.setFontSize(self.fontBaseSize/self.dpi, self.pdc)
        longest=0; w=50
        for comp in self.routine:
            name = comp.params['name'].val
            if len(name)>longest:
                longest=len(name)
                w = self.GetFullTextExtent(name)[0]
        self.timeXpos = w+(50,50,90)[self.drawSize]

        #draw timeline at bottom of page
        yPosBottom = self.yPosTop+len(self.routine)*self.componentStep
        self.drawTimeGrid(self.pdc,self.yPosTop,yPosBottom)
        yPos = self.yPosTop

        for n, component in enumerate(self.routine):
            self.drawComponent(self.pdc, component, yPos)
            yPos+=self.componentStep

        self.SetVirtualSize((self.maxWidth, yPos+50))#the 50 allows space for labels below the time axis
        self.pdc.EndDrawing()
        self.Refresh()#refresh the visible window after drawing (using OnPaint)

    def drawTimeGrid(self, dc, yPosTop, yPosBottom, labelAbove=True):
        """Draws the grid of lines and labels the time axes
        """
        tMax=self.getMaxTime()*1.1
        xScale = self.getSecsPerPixel()
        xSt=self.timeXposStart
        xEnd=self.timeXposEnd
        dc.SetPen(wx.Pen(wx.Color(0, 0, 0, 150)))
        #draw horizontal lines on top and bottom
        dc.DrawLine(x1=xSt,y1=yPosTop,
                    x2=xEnd,y2=yPosTop)
        dc.DrawLine(x1=xSt,y1=yPosBottom,
                    x2=xEnd,y2=yPosBottom)
        #draw vertical time points
        unitSize = 10**numpy.ceil(numpy.log10(tMax*0.8))/10.0#gives roughly 1/10 the width, but in rounded to base 10 of 0.1,1,10...
        if tMax/unitSize<3: unitSize = 10**numpy.ceil(numpy.log10(tMax*0.8))/50.0#gives units of 2 (0.2,2,20)
        elif tMax/unitSize<6: unitSize = 10**numpy.ceil(numpy.log10(tMax*0.8))/20.0#gives units of 5 (0.5,5,50)
        for lineN in range(int(numpy.floor(tMax/unitSize))):
            dc.DrawLine(xSt+lineN*unitSize/xScale, yPosTop-4,#vertical line
                    xSt+lineN*unitSize/xScale, yPosBottom+4)
            dc.DrawText('%.2g' %(lineN*unitSize),xSt+lineN*unitSize/xScale-4,yPosTop-20)#label above
            if yPosBottom>300:#if bottom of grid is far away then draw labels here too
                dc.DrawText('%.2g' %(lineN*unitSize),xSt+lineN*unitSize/xScale-4,yPosBottom+10)#label below
        #add a label
        self.setFontSize(self.fontBaseSize/self.dpi, dc)
        dc.DrawText('t (sec)',xEnd+5,yPosTop-self.GetFullTextExtent('t')[1]/2.0)#y is y-half height of text
        # or draw bottom labels only if scrolling is turned on, virtual size > available size?
        if yPosBottom>300:#if bottom of grid is far away then draw labels here too
            dc.DrawText('t (sec)',xEnd+5,yPosBottom-self.GetFullTextExtent('t')[1]/2.0)#y is y-half height of text
    def setFontSize(self, size, dc):
        font = self.GetFont()
        font.SetPointSize(size)
        dc.SetFont(font)
    def drawComponent(self, dc, component, yPos):
        """Draw the timing of one component on the timeline"""

        #set an id for the region of this comonent (so it can act as a button)
        ##see if we created this already
        id=None
        for key in self.componentFromID.keys():
            if self.componentFromID[key]==component:
                id=key
        if not id: #then create one and add to the dict
            id = wx.NewId()
            self.componentFromID[id]=component
        dc.SetId(id)

        iconYOffset = (6,6,0)[self.drawSize]
        thisIcon = components.icons[component.getType()][str(self.iconSize)]#getType index 0 is main icon
        dc.DrawBitmap(thisIcon, self.iconXpos,yPos+iconYOffset, True)
        fullRect = wx.Rect(self.iconXpos, yPos, thisIcon.GetWidth(),thisIcon.GetHeight())

        self.setFontSize(self.fontBaseSize/self.dpi, dc)

        name = component.params['name'].val
        #get size based on text
        w,h = self.GetFullTextExtent(name)[0:2]
        #draw text
        x = self.iconXpos-self.dpi/10-w + (self.iconSize,self.iconSize,10)[self.drawSize]
        y = yPos+thisIcon.GetHeight()/2-h/2 + (5,5,-2)[self.drawSize]
        dc.DrawText(name, x-20, y)
        fullRect.Union(wx.Rect(x-20,y,w,h))

        #deduce start and stop times if possible
        startTime, duration = self.getStartAndDuration(component)
        #draw entries on timeline (if they have some time definition)
        if startTime!=None and duration!=None:#then we can draw a sensible time bar!
            xScale = self.getSecsPerPixel()
            dc.SetPen(wx.Pen(wx.Color(200, 100, 100, 0), style=wx.TRANSPARENT))
            dc.SetBrush(wx.Brush(routineTimeColor))
            hSize = (3.5,2.75,2)[self.drawSize]
            yOffset = (3,3,0)[self.drawSize]
            h = self.componentStep/hSize
            xSt = self.timeXposStart + startTime/xScale
            w = (duration)/xScale+1.85 # +1.85 to compensate for border alpha=0 in dc.SetPen
            if w>10000: w=10000#limit width to 10000 pixels!
            if w<2: w=2#make sure at least one pixel shows
            dc.DrawRectangle(xSt, y+yOffset, w,h )
            fullRect.Union(wx.Rect(xSt, y+yOffset, w,h ))#update bounds to include time bar
        dc.SetIdBounds(id,fullRect)

    def editComponentProperties(self, event=None, component=None):
        if event:#we got here from a wx.button press (rather than our own drawn icons)
            componentName=event.EventObject.GetName()
            component=self.routine.getComponentFromName(componentName)
        #does this component have a help page?
        if hasattr(component, 'url'):helpUrl=component.url
        else:helpUrl=None
        old_name = component.params['name'].val
        #create the dialog
        dlg = DlgComponentProperties(frame=self.frame,
            title=component.params['name'].val+' Properties',
            params = component.params,
            order = component.order,
            helpUrl=helpUrl, editing=True)
        if dlg.OK:
            self.redrawRoutine()#need to refresh timings section
            self.Refresh()#then redraw visible
            self.frame.exp.namespace.remove(old_name)
            self.frame.exp.namespace.add(component.params['name'].val)
            self.frame.addToUndoStack("edit %s" %component.params['name'])

    def getSecsPerPixel(self):
        return float(self.getMaxTime())/(self.timeXposEnd-self.timeXposStart)
    def getMaxTime(self):
        """What the last (predetermined) stimulus time to be presented. If
        there are no components or they have code-based times then will default
        to 10secs
        """
        maxTime=0
        for n, component in enumerate(self.routine):
            if component.params.has_key('startType'):
                start, duration = self.getStartAndDuration(component)
                if duration==FOREVER:
                    continue#this shouldn't control the end of the time grid
                try:thisT=start+duration#will fail if either value is not defined
                except:thisT=0
                maxTime=max(maxTime,thisT)
        if maxTime==0:#if there are no components
            maxTime=10
        return maxTime
    def getStartAndDuration(self, component):
        """Determine the start and duration of the stimulus
        purely for Routine rendering purposes in the app (does not affect
        actual drawing during the experiment)
        """
        if not component.params.has_key('startType'):
            return None, None#this component does not have any start/stop
        startType=component.params['startType'].val
        stopType=component.params['stopType'].val
        #deduce a start time (s) if possible
        #user has given a time estimate
        if canBeNumeric(component.params['startEstim'].val):
            startTime=float(component.params['startEstim'].val)
        elif startType=='time (s)' and canBeNumeric(component.params['startVal'].val):
            startTime=float(component.params['startVal'].val)
        else: startTime=None
        #deduce duration (s) if possible. Duration used because box needs width
        if canBeNumeric(component.params['durationEstim'].val):
            duration=float(component.params['durationEstim'].val)
        elif component.params['stopVal'].val in ['','-1','None']:
            duration=FOREVER#infinite duration
        elif stopType=='time (s)' and canBeNumeric(component.params['stopVal'].val):
            duration=float(component.params['stopVal'].val)-startTime
        elif stopType=='duration (s)' and canBeNumeric(component.params['stopVal'].val):
            duration=float(component.params['stopVal'].val)
        else:
            duration=None
        return startTime, duration

class RoutinesNotebook(wx.aui.AuiNotebook):
    """A notebook that stores one or more routines
    """
    def __init__(self, frame, id=-1):
        self.frame=frame
        self.app=frame.app
        self.routineMaxSize = 2
        self.appData = self.app.prefs.appData
        wx.aui.AuiNotebook.__init__(self, frame, id)

        self.Bind(wx.aui.EVT_AUINOTEBOOK_PAGE_CLOSE, self.onClosePane)
        if not hasattr(self.frame, 'exp'):
            return#we haven't yet added an exp
    def getCurrentRoutine(self):
        routinePage=self.getCurrentPage()
        if routinePage:
            return routinePage.routine
        else: #no routine page
            return None
    def setCurrentRoutine(self, routine):
        for ii in range(self.GetPageCount()):
            if routine is self.GetPage(ii).routine:
                self.SetSelection(ii)
    def getCurrentPage(self):
        if self.GetSelection()>=0:
            return self.GetPage(self.GetSelection())
        else:#there are no routine pages
            return None
    def addRoutinePage(self, routineName, routine):
#        routinePage = RoutinePage(parent=self, routine=routine)
        routinePage = RoutineCanvas(notebook=self, routine=routine)
        self.AddPage(routinePage, routineName)
    def removePages(self):
        for ii in range(self.GetPageCount()):
            currId = self.GetSelection()
            self.DeletePage(currId)
    def createNewRoutine(self, returnName=False):
        dlg = wx.TextEntryDialog(self, message="What is the name for the new Routine? (e.g. instr, trial, feedback)",
            caption='New Routine')
        exp = self.frame.exp
        routineName = None
        if dlg.ShowModal() == wx.ID_OK:
            routineName=dlg.GetValue()
            # silently auto-adjust the name to be valid, and register in the namespace:
            routineName = exp.namespace.makeValid(routineName, prefix='routine')
            exp.namespace.add(routineName) #add to the namespace
            exp.addRoutine(routineName)#add to the experiment
            self.addRoutinePage(routineName, exp.routines[routineName])#then to the notebook
            self.frame.addToUndoStack("created %s routine" %routineName)
        dlg.Destroy()
        if returnName:
            return routineName
    def onClosePane(self, event=None):
        """Close the pane and remove the routine from the exp
        """
        routine = self.GetPage(event.GetSelection()).routine
        name=routine.name
        #update experiment object, namespace, and flow window (if this is being used)
        if name in self.frame.exp.routines.keys():
            # remove names of the routine and all its components from namespace
            for c in self.frame.exp.routines[name]:
                self.frame.exp.namespace.remove(c.params['name'].val)
            self.frame.exp.namespace.remove(self.frame.exp.routines[name].name)
            del self.frame.exp.routines[name]
        if routine in self.frame.exp.flow:
            self.frame.exp.flow.removeComponent(routine)
            self.frame.flowPanel.draw()
        self.frame.addToUndoStack("remove routine %s" %(name))
    def increaseSize(self, event=None):
        self.appData['routineSize'] = min(self.routineMaxSize, self.appData['routineSize'] + 1)
        self.frame.Freeze()
        self.redrawRoutines()
        self.frame.Thaw()
    def decreaseSize(self, event=None):
        self.appData['routineSize'] = max(0, self.appData['routineSize'] - 1)
        self.frame.Freeze()
        self.redrawRoutines()
        self.frame.Thaw()
    def redrawRoutines(self):
        """Removes all the routines, adds them back and sets current back to orig
        """
        currPage = self.GetSelection()
        self.removePages()
        for routineName in self.frame.exp.routines:
            self.addRoutinePage(routineName, self.frame.exp.routines[routineName])
        if currPage>-1:
            self.SetSelection(currPage)
class ComponentsPanel(scrolledpanel.ScrolledPanel):
    def __init__(self, frame, id=-1):
        """A panel that displays available components.
        """
        self.frame=frame
        self.app=frame.app
        self.dpi=self.app.dpi
        scrolledpanel.ScrolledPanel.__init__(self,frame,id,size=(1.1*self.dpi,10*self.dpi))
        if self.app.prefs.app['largeIcons']:
            self.sizer=wx.BoxSizer(wx.VERTICAL)
        else:
            self.sizer=wx.FlexGridSizer(cols=2)
        # add a button for each type of event that can be added
        self.componentButtons={}; self.componentFromID={}
        self.components=experiment.getAllComponents()
        for hiddenComp in self.frame.prefs['hiddenComponents']:
            del self.components[hiddenComp]
        del self.components['SettingsComponent']#also remove settings - that's in toolbar not components panel
        for thisName in self.components.keys():
            #NB thisComp is a class - we can't use its methods until it is an instance
            thisComp=self.components[thisName]
            shortName=thisName#but might be shortened below
            for redundant in ['component','Component']:
                if redundant in thisName: shortName=thisName.replace(redundant, "")
#            thisIcon.SetSize((16,16))
            if self.app.prefs.app['largeIcons']:
                thisIcon = components.icons[thisName]['48add']#index 1 is the 'add' icon
            else:
                thisIcon = components.icons[thisName]['24add']#index 1 is the 'add' icon
            btn = wx.BitmapButton(self, -1, thisIcon,
                           size=(thisIcon.GetWidth()+10, thisIcon.GetHeight()+10),
                           name=thisComp.__name__)
            if thisName in components.tooltips:
                thisTip = components.tooltips[thisName]
            else:
                thisTip = shortName
            btn.SetToolTip(wx.ToolTip(thisTip))
            self.componentFromID[btn.GetId()]=thisName
            self.Bind(wx.EVT_BUTTON, self.onComponentAdd,btn)
            self.sizer.Add(btn, proportion=0, flag=wx.ALIGN_TOP)#,wx.EXPAND|wx.ALIGN_CENTER )
            self.componentButtons[thisName]=btn#store it for elsewhere

        self.SetSizer(self.sizer)
        self.SetAutoLayout(1)
        self.SetupScrolling()
        self.SetDropTarget(FileDropTarget(builder = self.frame))

    def onComponentAdd(self,evt):
        #get name of current routine
        currRoutinePage = self.frame.routinePanel.getCurrentPage()
        if not currRoutinePage:
            dialogs.MessageDialog(self,"Create a routine (Experiment menu) before adding components",
                type='Info', title='Error').ShowModal()
            return False
        currRoutine = self.frame.routinePanel.getCurrentRoutine()
        #get component name
        newClassStr = self.componentFromID[evt.GetId()]
        componentName = newClassStr.replace('Component','')
        newCompClass = self.components[newClassStr]
        newComp = newCompClass(parentName=currRoutine.name, exp=self.frame.exp)
        #does this component have a help page?
        if hasattr(newComp, 'url'):helpUrl=newComp.url
        else:
            helpUrl=None
        #create component template
        dlg = DlgComponentProperties(frame=self.frame,
            title=componentName+' Properties',
            params = newComp.params,
            order = newComp.order,
            helpUrl=helpUrl)

        compName = newComp.params['name']
        if dlg.OK:
            currRoutine.addComponent(newComp)#add to the actual routing
            namespace = self.frame.exp.namespace
            newComp.params['name'].val = namespace.makeValid(newComp.params['name'].val)
            namespace.add(newComp.params['name'].val)
            currRoutinePage.redrawRoutine()#update the routine's view with the new component too
#            currRoutinePage.Refresh()#done at the end of redrawRoutine
            self.frame.addToUndoStack("added %s to %s" %(compName, currRoutine.name))
        return True
class ParamCtrls:
    def __init__(self, dlg, label, param, browse=False, noCtrls=False, advanced=False):
        """Create a set of ctrls for a particular Component Parameter, to be
        used in Component Properties dialogs. These need to be positioned
        by the calling dlg.

        e.g.::

            param = experiment.Param(val='boo', valType='str')
            ctrls=ParamCtrls(dlg=self, label=fieldName,param=param)
            self.paramCtrls[fieldName] = ctrls #keep track of them in the dlg
            self.sizer.Add(ctrls.nameCtrl, (self.currRow,0), (1,1),wx.ALIGN_RIGHT )
            self.sizer.Add(ctrls.valueCtrl, (self.currRow,1) )
            #these are optional (the parameter might be None)
            if ctrls.typeCtrl: self.sizer.Add(ctrls.typeCtrl, (self.currRow,2) )
            if ctrls.updateCtrl: self.sizer.Add(ctrls.updateCtrl, (self.currRow,3))

        If browse is True then a browseCtrl will be added (you need to bind events yourself)
        If noCtrls is True then no actual wx widgets are made, but attribute names are created
        """
        self.param = param
        self.dlg = dlg
        self.dpi=self.dlg.dpi
        self.valueWidth = self.dpi*3.5
        if advanced: parent=self.dlg.advPanel.GetPane()
        else: parent=self.dlg
        #param has the fields:
        #val, valType, allowedVals=[],allowedTypes=[], hint="", updates=None, allowedUpdates=None
        # we need the following
        self.nameCtrl = self.valueCtrl = self.typeCtrl = self.updateCtrl = None
        self.browseCtrl = None
        if noCtrls: return#we don't need to do any more

        if type(param.val)==numpy.ndarray:
            initial=initial.tolist() #convert numpy arrays to lists
        labelLength = wx.Size(self.dpi*2,self.dpi*2/3)#was 8*until v0.91.4
        if param.valType == 'code' and label != 'name':
            displayLabel = label+' $'
        else:
            displayLabel = label
        self.nameCtrl = wx.StaticText(parent,-1,displayLabel,size=None,
                                        style=wx.ALIGN_RIGHT)

        if label in ['text', 'customize_everything']:
            #for text input we need a bigger (multiline) box
            self.valueCtrl = wx.TextCtrl(parent,-1,unicode(param.val),
                style=wx.TE_MULTILINE,
                size=wx.Size(self.valueWidth,-1))
            if label == 'text':
                self.valueCtrl.SetFocus()
            #expando seems like a nice idea - but probs with pasting in text and with resizing
            #self.valueCtrl = ExpandoTextCtrl(parent,-1,str(param.val),
            #    style=wx.TE_MULTILINE,
            #    size=wx.Size(500,-1))
            #self.valueCtrl.SetMaxHeight(500)
        elif label in components.code.codeParamNames[:]:
            #code input fields one day change these to wx.stc fields?
            self.valueCtrl = wx.TextCtrl(parent,-1,unicode(param.val),
                style=wx.TE_MULTILINE,
                size=wx.Size(self.valueWidth,-1))
        elif param.valType=='bool':
            #only True or False - use a checkbox
             self.valueCtrl = wx.CheckBox(parent, size = wx.Size(self.valueWidth,-1))
             self.valueCtrl.SetValue(param.val)
        elif len(param.allowedVals)>1:
            #there are limitted options - use a Choice control
            self.valueCtrl = wx.Choice(parent, choices=param.allowedVals, size=wx.Size(self.valueWidth,-1))
            self.valueCtrl.SetStringSelection(unicode(param.val))
        else:
            #create the full set of ctrls
            val = unicode(param.val)
            if label == 'conditionsFile':
                val = getAbbrev(val)
            self.valueCtrl = wx.TextCtrl(parent,-1,val,size=wx.Size(self.valueWidth,-1))
            if label in ['allowedKeys', 'image', 'movie', 'scaleDescription', 'sound', 'Begin Routine']:
                self.valueCtrl.SetFocus()
        self.valueCtrl.SetToolTipString(param.hint)
        if len(param.allowedVals)==1:
            self.valueCtrl.Disable()#visible but can't be changed

        #create the type control
        if len(param.allowedTypes)==0:
            pass
        else:
            self.typeCtrl = wx.Choice(parent, choices=param.allowedTypes)
            self.typeCtrl.SetStringSelection(param.valType)
        if len(param.allowedTypes)==1:
            self.typeCtrl.Disable()#visible but can't be changed

        #create update control
        if param.allowedUpdates==None or len(param.allowedUpdates)==0:
            pass
        else:
            self.updateCtrl = wx.Choice(parent, choices=param.allowedUpdates)
            self.updateCtrl.SetStringSelection(param.updates)
        if param.allowedUpdates!=None and len(param.allowedUpdates)==1:
            self.updateCtrl.Disable()#visible but can't be changed
        #create browse control
        if browse:
            self.browseCtrl = wx.Button(parent, -1, "Browse...") #we don't need a label for this
    def _getCtrlValue(self, ctrl):
        """Retrieve the current value form the control (whatever type of ctrl it
        is, e.g. checkbox.GetValue, textctrl.GetStringSelection
        """
        """Different types of control have different methods for retrieving value.
        This function checks them all and returns the value or None.
        """
        if ctrl==None: return None
        elif hasattr(ctrl, 'GetValue'): #e.g. TextCtrl
            return ctrl.GetValue()
        elif hasattr(ctrl, 'GetStringSelection'): #for wx.Choice
            return ctrl.GetStringSelection()
        elif hasattr(ctrl, 'GetLabel'): #for wx.StaticText
            return ctrl.GetLabel()
        else:
            print "failed to retrieve the value for %s: %s" %(fieldName, ctrls.valueCtrl)
            return None
    def _setCtrlValue(self, ctrl, newVal):
        """Set the current value form the control (whatever type of ctrl it
        is, e.g. checkbox.SetValue, textctrl.SetStringSelection
        """
        """Different types of control have different methods for retrieving value.
        This function checks them all and returns the value or None.
        """
        if ctrl==None: return None
        elif hasattr(ctrl, 'SetValue'): #e.g. TextCtrl
            ctrl.SetValue(newVal)
        elif hasattr(ctrl, 'SetStringSelection'): #for wx.Choice
            ctrl.SetStringSelection(newVal)
        elif hasattr(ctrl, 'SetLabel'): #for wx.StaticText
            ctrl.SetLabel(newVal)
        else:
            print "failed to retrieve the value for %s: %s" %(fieldName, ctrls.valueCtrl)
    def getValue(self):
        """Get the current value of the value ctrl
        """
        return self._getCtrlValue(self.valueCtrl)
    def setValue(self, newVal):
        """Get the current value of the value ctrl
        """
        return self._setCtrlValue(self.valueCtrl, newVal)
    def getType(self):
        """Get the current value of the type ctrl
        """
        if self.typeCtrl:
            return self._getCtrlValue(self.typeCtrl)
    def getUpdates(self):
        """Get the current value of the updates ctrl
        """
        if self.updateCtrl:
            return self._getCtrlValue(self.updateCtrl)
    def setVisible(self, newVal=True):
        self.valueCtrl.Show(newVal)
        self.nameCtrl.Show(newVal)
        if self.updateCtrl: self.updateCtrl.Show(newVal)
        if self.typeCtrl: self.typeCtrl.Show(newVal)

class _BaseParamsDlg(wx.Dialog):
    def __init__(self,frame,title,params,order,
            helpUrl=None, suppressTitles=True,
            showAdvanced=False,
            pos=wx.DefaultPosition, size=wx.DefaultSize,
            style=wx.DEFAULT_DIALOG_STYLE|wx.DIALOG_NO_PARENT|wx.TAB_TRAVERSAL,editing=False):
        wx.Dialog.__init__(self, frame,-1,title,pos,size,style)
        self.frame=frame
        self.app=frame.app
        self.dpi=self.app.dpi
        self.helpUrl=helpUrl
        self.Center()
        self.panel = wx.Panel(self, -1)
        self.params=params   #dict
        self.title = title
        if not editing and title != 'Experiment Settings' and 'name' in self.params.keys():
            # then we're adding a new component, so provide a known-valid name:
            self.params['name'].val = self.frame.exp.namespace.makeValid(params['name'].val)
        self.paramCtrls={}
        self.showAdvanced=showAdvanced
        self.order=order
        self.data = []
        self.ctrlSizer= wx.GridBagSizer(vgap=2,hgap=2)
        self.ctrlSizer.AddGrowableCol(1)#valueCtrl column
        self.currRow = 0
        self.advCtrlSizer= wx.GridBagSizer(vgap=2,hgap=2)
        self.advCurrRow = 0
        self.nameOKlabel=None
        self.maxFieldLength = 10#max( len(str(self.params[x])) for x in keys )
        types=dict([])
        self.useUpdates=False#does the dlg need an 'updates' row (do any params use it?)
        self.timeParams=['startType','startVal','stopType','stopVal']
        self.codeParamNames = components.code.codeParamNames[:] # want a copy
        self.codeFieldNameFromID = {}
        self.codeIDFromFieldName = {}

        #create a header row of titles
        if not suppressTitles:
            size=wx.Size(1.5*self.dpi,-1)
            self.ctrlSizer.Add(wx.StaticText(self,-1,'Parameter',size=size, style=wx.ALIGN_CENTER),(self.currRow,0))
            self.ctrlSizer.Add(wx.StaticText(self,-1,'Value',size=size, style=wx.ALIGN_CENTER),(self.currRow,1))
            #self.sizer.Add(wx.StaticText(self,-1,'Value Type',size=size, style=wx.ALIGN_CENTER),(self.currRow,3))
            self.ctrlSizer.Add(wx.StaticText(self,-1,'Updates',size=size, style=wx.ALIGN_CENTER),(self.currRow,2))
            self.currRow+=1
            self.ctrlSizer.Add(
                wx.StaticLine(self, size=wx.Size(100,20)),
                (self.currRow,0),(1,2), wx.ALIGN_CENTER|wx.EXPAND)
        self.currRow+=1

        #get all params and sort
        remaining = sorted(self.params.keys())
        #check for advanced params
        if 'advancedParams' in self.params.keys():
            self.advParams=self.params['advancedParams']
            remaining.remove('advancedParams')
        else:self.advParams=[]

        #start with the name (always)
        if 'name' in remaining:
            self.addParam('name')
            remaining.remove('name')
            if 'name' in self.order:
                self.order.remove('name')
#            self.currRow+=1
        #add start/stop info
        if 'startType' in remaining:
            remaining = self.addStartStopCtrls(remaining=remaining)
            #self.ctrlSizer.Add(
            #    wx.StaticLine(self, size=wx.Size(100,10)),
            #    (self.currRow,0),(1,3), wx.ALIGN_CENTER|wx.EXPAND)
            self.currRow+=1#an extra row to create space (staticLine didn't look right)
        #loop through the prescribed order (the most important?)
        for fieldName in self.order:
            if fieldName in self.advParams:continue#skip advanced params
            self.addParam(fieldName)
            remaining.remove(fieldName)
        #add any params that weren't specified in the order
        for fieldName in remaining:
            if fieldName not in self.advParams:
                self.addParam(fieldName)
        #add advanced params if needed
        if len(self.advParams)>0:
            self.addAdvancedTab()
            for fieldName in self.advParams:
                self.addParam(fieldName, advanced=True)

    def addStartStopCtrls(self,remaining):
        """Add controls for startType, startVal, stopType, stopVal
        remaining refers to
        """
        sizer=self.ctrlSizer
        parent=self
        currRow = self.currRow

        ##Start point
        startTypeParam = self.params['startType']
        startValParam = self.params['startVal']
        #create label
        label = wx.StaticText(self,-1,'Start', style=wx.ALIGN_CENTER)
        labelEstim = wx.StaticText(self,-1,'Expected start (s)', style=wx.ALIGN_CENTER)
        labelEstim.SetForegroundColour('gray')
        #the method to be used to interpret this start/stop
        self.startTypeCtrl = wx.Choice(parent, choices=startTypeParam.allowedVals)
        self.startTypeCtrl.SetStringSelection(startTypeParam.val)
        #the value to be used as the start/stop
        self.startValCtrl = wx.TextCtrl(parent,-1,unicode(startValParam.val))
        self.startValCtrl.SetToolTipString(self.params['startVal'].hint)
        #the value to estimate start/stop if not numeric
        self.startEstimCtrl = wx.TextCtrl(parent,-1,unicode(self.params['startEstim'].val))
        self.startEstimCtrl.SetToolTipString(self.params['startEstim'].hint)
        #add the controls to a new line
        startSizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        startSizer.Add(self.startTypeCtrl)
        startSizer.Add(self.startValCtrl, 1,flag=wx.EXPAND)
        startEstimSizer=wx.BoxSizer(orient=wx.HORIZONTAL)
        startEstimSizer.Add(labelEstim)
        startEstimSizer.Add(self.startEstimCtrl)
        startAllCrtlSizer = wx.BoxSizer(orient=wx.VERTICAL)
        startAllCrtlSizer.Add(startSizer,flag=wx.EXPAND)
        startAllCrtlSizer.Add(startEstimSizer, flag=wx.ALIGN_RIGHT)
        self.ctrlSizer.Add(label, (self.currRow,0),(1,1),wx.ALIGN_RIGHT)
        #add our new row
        self.ctrlSizer.Add(startAllCrtlSizer,(self.currRow,1),(1,1),flag=wx.EXPAND)
        self.currRow+=1
        remaining.remove('startType')
        remaining.remove('startVal')
        remaining.remove('startEstim')

        ##Stop point
        stopTypeParam = self.params['stopType']
        stopValParam = self.params['stopVal']
        #create label
        label = wx.StaticText(self,-1,'Stop', style=wx.ALIGN_CENTER)
        labelEstim = wx.StaticText(self,-1,'Expected duration (s)', style=wx.ALIGN_CENTER)
        labelEstim.SetForegroundColour('gray')
        #the method to be used to interpret this start/stop
        self.stopTypeCtrl = wx.Choice(parent, choices=stopTypeParam.allowedVals)
        self.stopTypeCtrl.SetStringSelection(stopTypeParam.val)
        #the value to be used as the start/stop
        self.stopValCtrl = wx.TextCtrl(parent,-1,unicode(stopValParam.val))
        self.stopValCtrl.SetToolTipString(self.params['stopVal'].hint)
        #the value to estimate start/stop if not numeric
        self.durationEstimCtrl = wx.TextCtrl(parent,-1,unicode(self.params['durationEstim'].val))
        self.durationEstimCtrl.SetToolTipString(self.params['durationEstim'].hint)
        #add the controls to a new line
        stopSizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        stopSizer.Add(self.stopTypeCtrl)
        stopSizer.Add(self.stopValCtrl, 1,flag=wx.EXPAND)
        stopEstimSizer=wx.BoxSizer(orient=wx.HORIZONTAL)
        stopEstimSizer.Add(labelEstim)
        stopEstimSizer.Add(self.durationEstimCtrl)
        stopAllCrtlSizer = wx.BoxSizer(orient=wx.VERTICAL)
        stopAllCrtlSizer.Add(stopSizer,flag=wx.EXPAND)
        stopAllCrtlSizer.Add(stopEstimSizer, flag=wx.ALIGN_RIGHT)
        self.ctrlSizer.Add(label, (self.currRow,0),(1,1),wx.ALIGN_RIGHT)
        #add our new row
        self.ctrlSizer.Add(stopAllCrtlSizer,(self.currRow,1),(1,1),flag=wx.EXPAND)
        self.currRow+=1
        remaining.remove('stopType')
        remaining.remove('stopVal')
        remaining.remove('durationEstim')
        return remaining

    def addParam(self,fieldName, advanced=False):
        """Add a parameter to the basic sizer
        """
        if advanced:
            sizer=self.advCtrlSizer
            parent=self.advPanel.GetPane()
            currRow = self.advCurrRow
        else:
            sizer=self.ctrlSizer
            parent=self
            currRow = self.currRow
        param=self.params[fieldName]
        if param.label not in [None, '']:
            label=param.label
        else:
            label=fieldName
        ctrls=ParamCtrls(dlg=self, label=label,param=param, advanced=advanced)
        self.paramCtrls[fieldName] = ctrls
        if fieldName=='name':
            ctrls.valueCtrl.Bind(wx.EVT_TEXT, self.checkName)
        # self.valueCtrl = self.typeCtrl = self.updateCtrl
        sizer.Add(ctrls.nameCtrl, (currRow,0), (1,1),wx.ALIGN_RIGHT| wx.LEFT|wx.RIGHT,border=5 )
        sizer.Add(ctrls.valueCtrl, (currRow,1) , flag=wx.EXPAND| wx.LEFT|wx.RIGHT,border=5)
        if ctrls.updateCtrl:
            sizer.Add(ctrls.updateCtrl, (currRow,2))
        if ctrls.typeCtrl:
            sizer.Add(ctrls.typeCtrl, (currRow,3) )
        if fieldName=='text':
            sizer.AddGrowableRow(currRow)#doesn't seem to work though
            #self.Bind(EVT_ETC_LAYOUT_NEEDED, self.onNewTextSize, ctrls.valueCtrl)
        elif fieldName=='color':
            ctrls.valueCtrl.Bind(wx.EVT_RIGHT_DOWN, self.launchColorPicker)
        elif fieldName=='Experiment info':
            ctrls.valueCtrl.Bind(wx.EVT_RIGHT_DOWN, self.previewExpInfo)
        elif fieldName in self.codeParamNames:
            ctrls.valueCtrl.Bind(wx.EVT_RIGHT_DOWN, self.checkCodeSyntax)
            ctrls.valueCtrl.Bind(wx.EVT_TEXT, self.onTextEventCode)
            ctrls.valueCtrl.Bind(wx.EVT_NAVIGATION_KEY, self.onNavigationCode) #catch Tab
            id = wx.NewId()
            self.codeFieldNameFromID[id] = fieldName
            self.codeIDFromFieldName[fieldName] = id
            ctrls.valueCtrl.SetId(id)
            #print id, fieldName
        elif fieldName=='Monitor':
            ctrls.valueCtrl.Bind(wx.EVT_RIGHT_DOWN, self.openMonitorCenter)
        #increment row number
        if advanced: self.advCurrRow+=1
        else:self.currRow+=1

    def openMonitorCenter(self,event):
        self.app.openMonitorCenter(event)
        self.paramCtrls['Monitor'].valueCtrl.SetFocus()
        # need to delay until the user closes the monitor center
        #self.paramCtrls['Monitor'].valueCtrl.Clear()
        #if wx.TheClipboard.Open():
        #    dataObject = wx.TextDataObject()
        #    if wx.TheClipboard.GetData(dataObject):
        #        self.paramCtrls['Monitor'].valueCtrl.WriteText(dataObject.GetText())
        #    wx.TheClipboard.Close()

    def previewExpInfo(self, event):
        thisValueCtrl = self.paramCtrls['Experiment info'].valueCtrl
        expInfo = thisValueCtrl.GetValue()
        needsUpdate = False
        if expInfo.strip()=='':
            expInfo = "{'participant':'', 'session':'001'}"
            title = 'providing default values...'
        else:
            title = 'PREVIEW' # not actually checked yet
        if not expInfo.lstrip().startswith('{'):
            expInfo = '{' + expInfo
            needsUpdate = True
        if not expInfo.strip().endswith('}'):
            expInfo += '}'
            needsUpdate = True
        try:
            newInfo = dict(eval(expInfo))
        except SyntaxError:
            # try to be helpful, but dict syntax is not so intuitive
            dlg = gui.Dlg(title="oops, syntax error...")
            dlg.addText('') # spacer
            dlg.addText("Experiment info needs to have python 'dict' syntax.")
            dlg.addText("(Delete everything and preview again to reset.)")
            dlg.addText("- items are pairs of the form 'a1': 'b', 'a2': b, 'a3': u'b',")
            dlg.addText("  (u' ' is unicode), with pairs separated by commas")
            dlg.addText("- the a's must be unique ('a1', 'a2', 'a3', ...)")
            dlg.addText("- the b's must be well-formed (str, int, float, list)")
            dlg.addText("- enclose everything in {   }")
            dlg.show()
            return
        # show preview
        previewDlg = gui.DlgFromDict(dictionary=newInfo, title=title)
        # if user made edits to values and then clicked OK, save them:
        if previewDlg.OK or needsUpdate:
            thisValueCtrl.SetFocus()
            thisValueCtrl.Clear()
            thisValueCtrl.WriteText(str(newInfo))

    def launchColorPicker(self, event):
        # bring up a colorPicker
        rgb = self.app.colorPicker(None) # str, remapped to -1..+1
        self.paramCtrls['color'].valueCtrl.SetFocus()
        self.paramCtrls['color'].valueCtrl.Clear()
        self.paramCtrls['color'].valueCtrl.WriteText('$'+rgb) # $ flag as code
        ii = self.paramCtrls['colorSpace'].valueCtrl.FindString('rgb')
        self.paramCtrls['colorSpace'].valueCtrl.SetSelection(ii)

    def onNewTextSize(self, event):
        self.Fit()#for ExpandoTextCtrl this is needed

    def addText(self, text, size=None):
        if size==None:
            size = wx.Size(8*len(text)+16, 25)
        myTxt = wx.StaticText(self,-1,
                                label=text,
                                style=wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_CENTER_HORIZONTAL,
                                size=size)
        self.ctrlSizer.Add(myTxt,wx.EXPAND)#add to current row spanning entire
        return myTxt
    def addAdvancedTab(self):
        self.advPanel = wx.CollapsiblePane(self, label='Show Advanced')
        self.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, self.onToggleAdvanced, self.advPanel)
        pane = self.advPanel.GetPane()
        pane.SetSizer(self.advCtrlSizer)
        self.advPanel.Collapse(not self.showAdvanced)
    def onToggleAdvanced(self, event=None):
        if self.advPanel.IsExpanded():
            self.advPanel.SetLabel('Hide Advanced')
            self.showAdvanced=True
        else:
            self.advPanel.SetLabel('Show Advanced')
            self.showAdvanced=False
    def show(self):
        """Adds an OK and cancel button, shows dialogue.

        This method returns wx.ID_OK (as from ShowModal), but also
        sets self.OK to be True or False
        """
        if 'name' in self.params.keys():
            if len(self.params['name'].val):
                nameInfo='Need a name'
            else: nameInfo=''
            self.nameOKlabel=wx.StaticText(self,-1,nameInfo,size=(300,25),
                                        style=wx.ALIGN_RIGHT)
            self.nameOKlabel.SetForegroundColour(wx.RED)

        #add buttons for OK and Cancel
        self.mainSizer=wx.BoxSizer(wx.VERTICAL)
        buttons = wx.StdDialogButtonSizer()
        #help button if we know the url
        if self.helpUrl!=None:
            helpBtn = wx.Button(self, wx.ID_HELP)
            helpBtn.SetToolTip(wx.ToolTip("Go to online help about this component"))
            helpBtn.Bind(wx.EVT_BUTTON, self.onHelp)
            buttons.Add(helpBtn, wx.ALIGN_LEFT|wx.ALL,border=3)
            buttons.AddSpacer(12)
        self.OKbtn = wx.Button(self, wx.ID_OK, " OK ")
        # intercept OK button if a loop dialog, in case file name was edited:
        if type(self) == DlgLoopProperties:
            self.OKbtn.Bind(wx.EVT_BUTTON, self.onOK)
        self.OKbtn.SetDefault()
        self.checkName() # disables OKbtn if bad name

        buttons.Add(self.OKbtn, 0, wx.ALL,border=3)
        CANCEL = wx.Button(self, wx.ID_CANCEL, " Cancel ")
        buttons.Add(CANCEL, 0, wx.ALL,border=3)
        buttons.Realize()
        #put it all together
        self.mainSizer.Add(self.ctrlSizer,flag=wx.GROW)#add main controls
        if hasattr(self, 'advParams') and len(self.advParams)>0:#add advanced controls
            self.mainSizer.Add(self.advPanel,0,flag=wx.GROW|wx.ALL,border=5)
        if self.nameOKlabel: self.mainSizer.Add(self.nameOKlabel, wx.ALIGN_RIGHT)
        self.mainSizer.Add(buttons, flag=wx.ALIGN_RIGHT)
        self.border = wx.BoxSizer(wx.VERTICAL)
        self.border.Add(self.mainSizer, flag=wx.ALL|wx.EXPAND, border=8)
        self.SetSizerAndFit(self.border)

        # run syntax check for a code component dialog:
        if hasattr(self, 'codeParamNames'):
            valTypes = [self.params[param].valType for param in self.params.keys()
                        if param in self.codeParamNames] # not configured to properly handle code fields except in code components
            if 'code' in valTypes:
                self.checkCodeSyntax()

        #do show and process return
        retVal = self.ShowModal()
        if retVal== wx.ID_OK: self.OK=True
        else:  self.OK=False
        return wx.ID_OK
    def onNavigationCode(self, event):
        #print event.GetId(),event.GetCurrentFocus() # 0 None
        return

        fieldName = self.codeFieldNameFromID[event.GetId()] #fails
        pos = self.paramCtrls[fieldName].valueCtrl.GetInsertionPoint()
        val = self.paramCtrls[fieldName].getValue()
        newVal = val[:pos] + '    ' + val[pos:]
        self.paramCtrls[fieldName].valueCtrl.ChangeValue(newVal)
        self.paramCtrls[fieldName].valueCtrl.SendTextUpdatedEvent()

    def onTextEventCode(self, event=None):
        """process text events for code components: change color to grey
        """
        #print event.GetId()
        fieldName = self.codeFieldNameFromID[event.GetId()]
        val = self.paramCtrls[fieldName].getValue()
        pos = self.paramCtrls[fieldName].valueCtrl.GetInsertionPoint()
        if pos >= 1 and val[pos-1] != "\n": # only do syntax check at end of line
            self.paramCtrls[fieldName].valueCtrl.SetBackgroundColour(wx.Color(215,215,215,255)) # grey, "changed"
        elif pos >= 2 and val[pos-2] != ":": # ... but skip the check if end of line is colon
            self._setNameColor(self._testCompile(fieldName))
    def _testCompile(self, fieldName):
        """checks code.val for legal python syntax, sets field bg color, returns status

        method: writes code to a file, try to py_compile it. not intended for
        high-freq repeated checking, ok for CPU but hits the disk every time.
        """
        # better to use a StringIO.StringIO() than a tmp file, but couldnt work it out
        # definitely don't want eval() or exec()
        tmpDir = mkdtemp(prefix='psychopy-check-code-syntax')
        tmpFile = os.path.join(tmpDir, 'tmp')
        val = self.paramCtrls[fieldName].getValue() # better than getParams(), which sets them, messes with cancel
        f = codecs.open(tmpFile, 'w', 'utf-8')
        f.write(val)
        f.close()
        #f=StringIO.StringIO(self.params[param].val) # tried to avoid a tmp file, no go
        try:
            py_compile.compile(tmpFile, doraise=True)
            self.paramCtrls[fieldName].valueCtrl.SetBackgroundColour(wx.Color(255,255,255, 255)) # white, ok
            syntaxCheck = True # syntax fine
        except: # hopefully SyntaxError, but can't check for it; checking messes with things
            self.paramCtrls[fieldName].valueCtrl.SetBackgroundColour(wx.Color(250,210,210, 255)) # red, bad
            syntaxCheck = False # syntax error
            # need to capture stderr to get the msg, which has line number etc
            #msg = py_compile.compile(tmpFile)
            #self.nameOKlabel.SetLabel(str(msg))
        # clean up tmp files:
        shutil.rmtree(tmpDir, ignore_errors=True)

        return syntaxCheck

    def checkCodeSyntax(self, event=None):
        """Checks syntax for whole code component by code box, sets box bg-color.
        """
        goodSyntax = True
        for fieldName in self.codeParamNames:
            if self.params[fieldName].valType != 'code':
                continue
            if not self.paramCtrls[fieldName].getValue().strip(): # if basically empty
                self.paramCtrls[fieldName].valueCtrl.SetBackgroundColour(wx.Color(255,255,255, 255)) # white
                continue # skip test
            goodSyntax = goodSyntax and self._testCompile(fieldName) # test syntax
        self._setNameColor(goodSyntax)
    def _setNameColor(self, goodSyntax):
        if goodSyntax:
            self.paramCtrls['name'].valueCtrl.SetBackgroundColour(wx.Color(220,250,220, 255)) # name green, good
            self.nameOKlabel.SetLabel("")
        else:
            self.paramCtrls['name'].valueCtrl.SetBackgroundColour(wx.Color(255,255,255, 255)) # name white
            self.nameOKlabel.SetLabel('syntax error')

    def getParams(self):
        """retrieves data from any fields in self.paramCtrls
        (populated during the __init__ function)

        The new data from the dlg get inserted back into the original params
        used in __init__ and are also returned from this method.
        """
        #get data from input fields
        for fieldName in self.params.keys():
            param=self.params[fieldName]
            if fieldName=='advancedParams':
                pass
            elif fieldName=='startType':
                param.val = self.startTypeCtrl.GetStringSelection()
            elif fieldName=='stopType':
                param.val = self.stopTypeCtrl.GetStringSelection()
            elif fieldName=='startVal':
                param.val = self.startValCtrl.GetValue()
            elif fieldName=='stopVal':
                param.val = self.stopValCtrl.GetValue()
            elif fieldName=='startEstim':
                param.val = self.startEstimCtrl.GetValue()
            elif fieldName=='durationEstim':
                param.val = self.durationEstimCtrl.GetValue()
            else:
                ctrls = self.paramCtrls[fieldName]#the various dlg ctrls for this param
                param.val = ctrls.getValue()
                if ctrls.typeCtrl: param.valType = ctrls.getType()
                if ctrls.updateCtrl: param.updates = ctrls.getUpdates()
        return self.params
    def _checkName(self, event=None, name=None):
        """checks namespace, return error-msg (str), enable (bool)
        """
        if event: newName = event.GetString()
        elif name: newName = name
        elif hasattr(self, 'paramCtrls'): newName=self.paramCtrls['name'].getValue()
        elif hasattr(self, 'globalCtrls'): newName=self.globalCtrls['name'].getValue()
        if newName=='':
            return "Missing name", False
        else:
            namespace = self.frame.exp.namespace
            used = namespace.exists(newName)
            same_as_old_name = bool(newName == self.params['name'].val)
            if used and not same_as_old_name:
                return "That name is in use (it's a %s). Try another name." % used, False
            elif not namespace.isValid(newName): # valid as a var name
                return "Name must be alpha-numeric or _, no spaces", False
            elif namespace.isPossiblyDerivable(newName): # warn but allow, chances are good that its actually ok
                return namespace.isPossiblyDerivable(newName), True
            else:
                return "", True
    def checkName(self, event=None):
        """check param name against namespace, legal var name
        """
        msg, enable = self._checkName(event=event)
        self.nameOKlabel.SetLabel(msg)
        if enable: self.OKbtn.Enable()
        else: self.OKbtn.Disable()
    def onHelp(self, event=None):
        """Uses self.app.followLink() to self.helpUrl
        """
        self.app.followLink(url=self.helpUrl)

class DlgLoopProperties(_BaseParamsDlg):
    def __init__(self,frame,title="Loop properties",loop=None,
            helpUrl=None,
            pos=wx.DefaultPosition, size=wx.DefaultSize,
            style=wx.DEFAULT_DIALOG_STYLE|wx.DIALOG_NO_PARENT|wx.RESIZE_BORDER):
        wx.Dialog.__init__(self, frame,-1,title,pos,size,style)
        self.helpUrl=helpUrl
        self.frame=frame
        self.exp=frame.exp
        self.app=frame.app
        self.dpi=self.app.dpi
        self.params={}
        self.Center()
        self.panel = wx.Panel(self, -1)
        self.globalCtrls={}
        self.constantsCtrls={}
        self.staircaseCtrls={}
        self.multiStairCtrls={}
        self.currentCtrls={}
        self.data = []
        self.ctrlSizer= wx.BoxSizer(wx.VERTICAL)
        self.conditions=None
        self.conditionsFile=None
        #create a valid new name; save old name in case we need to revert
        defaultName = 'trials'
        oldLoopName = defaultName
        if loop:
            oldLoopName = loop.params['name'].val
        namespace = frame.exp.namespace
        new_name = namespace.makeValid(oldLoopName)
        #create default instances of the diff loop types
        self.trialHandler=experiment.TrialHandler(exp=self.exp, name=new_name,
            loopType='random',nReps=5,conditions=[]) #for 'random','sequential', 'fullRandom'
        self.stairHandler=experiment.StairHandler(exp=self.exp, name=new_name,
            nReps=50, nReversals='',
            stepSizes='[0.8,0.8,0.4,0.4,0.2]', stepType='log', startVal=0.5) #for staircases
        self.multiStairHandler=experiment.MultiStairHandler(exp=self.exp, name=new_name,
            nReps=50, stairType='simple', switchStairs='random',
            conditions=[], conditionsFile='')
        #replace defaults with the loop we were given
        if loop==None:
            self.currentType='random'
            self.currentHandler=self.trialHandler
        elif loop.type=='TrialHandler':
            self.conditions=loop.params['conditions'].val
            self.conditionsFile=loop.params['conditionsFile'].val
            self.trialHandler = self.currentHandler = loop
            self.currentType=loop.params['loopType']#could be 'random', 'sequential', 'fullRandom'
        elif loop.type=='StairHandler':
            self.stairHandler = self.currentHandler = loop
            self.currentType='staircase'
        elif loop.type=='MultiStairHandler':
            self.multiStairHandler = self.currentHandler = loop
            self.currentType='interleaved staircase'
        elif loop.type=='QuestHandler':
            pass # what to do for quest?
        self.params['name']=self.currentHandler.params['name']

        self.makeGlobalCtrls()
        self.makeStaircaseCtrls()
        self.makeConstantsCtrls()#the controls for Method of Constants
        self.makeMultiStairCtrls()
        self.setCtrls(self.currentType)

        #show dialog and get most of the data
        self.show()
        if self.OK:
            self.params = self.getParams()
            #convert endPoints from str to list
            exec("self.params['endPoints'].val = %s" %self.params['endPoints'].val)
            #then sort the list so the endpoints are in correct order
            self.params['endPoints'].val.sort()
            if loop: # editing an existing loop
                namespace.remove(oldLoopName)
            namespace.add(self.params['name'].val)
            # don't always have a conditionsFile
            if hasattr(self, 'condNamesInFile'):
                namespace.add(self.condNamesInFile)
            if hasattr(self, 'duplCondNames'):
                namespace.remove(self.duplCondNames)
        else:
            if loop!=None:#if we had a loop during init then revert to its old name
                loop.params['name'].val = oldLoopName

        #make sure we set this back regardless of whether OK
        #otherwise it will be left as a summary string, not a conditions
        if self.currentHandler.params.has_key('conditionsFile'):
            self.currentHandler.params['conditions'].val=self.conditions

    def makeGlobalCtrls(self):
        for fieldName in ['name','loopType']:
            container=wx.BoxSizer(wx.HORIZONTAL)#to put them in
            self.globalCtrls[fieldName] = ctrls = ParamCtrls(self, fieldName,
                self.currentHandler.params[fieldName])
            container.AddMany( (ctrls.nameCtrl, ctrls.valueCtrl))
            self.ctrlSizer.Add(container)

        self.globalCtrls['name'].valueCtrl.Bind(wx.EVT_TEXT, self.checkName)
        self.Bind(wx.EVT_CHOICE, self.onTypeChanged, self.globalCtrls['loopType'].valueCtrl)

    def makeConstantsCtrls(self):
        #a list of controls for the random/sequential versions
        #that can be hidden or shown
        handler=self.trialHandler
        #loop through the params
        keys = handler.params.keys()
        #add conditions stuff to the *end*
        if 'conditions' in keys:
            keys.remove('conditions')
            keys.insert(-1,'conditions')
        if 'conditionsFile' in keys:
            keys.remove('conditionsFile')
            keys.insert(-1,'conditionsFile')
        #then step through them
        for fieldName in keys:
            if fieldName=='endPoints':continue#this was deprecated in v1.62.00
            if fieldName in self.globalCtrls.keys():
                #these have already been made and inserted into sizer
                ctrls=self.globalCtrls[fieldName]
            elif fieldName=='conditionsFile':
                container=wx.BoxSizer(wx.HORIZONTAL)
                ctrls=ParamCtrls(self, fieldName, handler.params[fieldName], browse=True)
                self.Bind(wx.EVT_BUTTON, self.onBrowseTrialsFile,ctrls.browseCtrl)
                ctrls.valueCtrl.Bind(wx.EVT_RIGHT_DOWN, self.viewConditions)
                container.AddMany((ctrls.nameCtrl, ctrls.valueCtrl, ctrls.browseCtrl))
                self.ctrlSizer.Add(container)
            elif fieldName=='conditions':
                if handler.params.has_key('conditions'):
                    text=self.getTrialsSummary(handler.params['conditions'].val)
                else:
                    text = """No parameters set"""
                ctrls = ParamCtrls(self, 'conditions',text,noCtrls=True)#we'll create our own widgets
                size = wx.Size(350, 50)
                ctrls.valueCtrl = self.addText(text, size)#NB this automatically adds to self.ctrlSizer
                #self.ctrlSizer.Add(ctrls.valueCtrl)
            else: #normal text entry field
                container=wx.BoxSizer(wx.HORIZONTAL)
                ctrls=ParamCtrls(self, fieldName, handler.params[fieldName])
                container.AddMany((ctrls.nameCtrl, ctrls.valueCtrl))
                self.ctrlSizer.Add(container)
            #store info about the field
            self.constantsCtrls[fieldName] = ctrls

    def makeMultiStairCtrls(self):
        #a list of controls for the random/sequential versions
        #that can be hidden or shown
        handler=self.multiStairHandler
        #loop through the params
        keys = handler.params.keys()
        #add conditions stuff to the *end*
        if 'conditions' in keys:
            keys.remove('conditions')
            keys.insert(-1,'conditions')
        if 'conditionsFile' in keys:
            keys.remove('conditionsFile')
            keys.insert(-1,'conditionsFile')
        #then step through them
        for fieldName in keys:
            if fieldName=='endPoints':continue#this was deprecated in v1.62.00
            if fieldName in self.globalCtrls.keys():
                #these have already been made and inserted into sizer
                ctrls=self.globalCtrls[fieldName]
            elif fieldName=='conditionsFile':
                container=wx.BoxSizer(wx.HORIZONTAL)
                ctrls=ParamCtrls(self, fieldName, handler.params[fieldName], browse=True)
                self.Bind(wx.EVT_BUTTON, self.onBrowseTrialsFile,ctrls.browseCtrl)
                container.AddMany((ctrls.nameCtrl, ctrls.valueCtrl, ctrls.browseCtrl))
                self.ctrlSizer.Add(container)
            elif fieldName=='conditions':
                if handler.params.has_key('conditions'):
                    text=self.getTrialsSummary(handler.params['conditions'].val)
                else:
                    text = """No parameters set (select a file above)"""
                ctrls = ParamCtrls(self, 'conditions',text,noCtrls=True)#we'll create our own widgets
                size = wx.Size(350, 50)
                ctrls.valueCtrl = self.addText(text, size)#NB this automatically adds to self.ctrlSizer
                #self.ctrlSizer.Add(ctrls.valueCtrl)
            else: #normal text entry field
                container=wx.BoxSizer(wx.HORIZONTAL)
                ctrls=ParamCtrls(self, fieldName, handler.params[fieldName])
                container.AddMany((ctrls.nameCtrl, ctrls.valueCtrl))
                self.ctrlSizer.Add(container)
            #store info about the field
            self.multiStairCtrls[fieldName] = ctrls
    def makeStaircaseCtrls(self):
        """Setup the controls for a StairHandler"""
        handler=self.stairHandler
        #loop through the params
        for fieldName in handler.params.keys():
            if fieldName=='endPoints':continue#this was deprecated in v1.62.00
            if fieldName in self.globalCtrls.keys():
                #these have already been made and inserted into sizer
                ctrls=self.globalCtrls[fieldName]
            else: #normal text entry field
                container=wx.BoxSizer(wx.HORIZONTAL)
                ctrls=ParamCtrls(self, fieldName, handler.params[fieldName])
                container.AddMany((ctrls.nameCtrl, ctrls.valueCtrl))
                self.ctrlSizer.Add(container)
            #store info about the field
            self.staircaseCtrls[fieldName] = ctrls
    def getTrialsSummary(self, conditions):
        if type(conditions)==list and len(conditions)>0:
            #get attr names (conditions[0].keys() inserts u'name' and u' is annoying for novice)
            paramStr = "["
            for param in conditions[0].keys():
                paramStr += (unicode(param)+', ')
            paramStr = paramStr[:-2]+"]"#remove final comma and add ]
            #generate summary info
            return '%i conditions, with %i parameters\n%s' \
                %(len(conditions),len(conditions[0]), paramStr)
        else:
            if self.conditionsFile and not os.path.isfile(self.conditionsFile):
                return  "No parameters set (conditionsFile not found)"
            return "No parameters set"
    def viewConditions(self, event):
        """ display Condition x Parameter values from within a file
        make new if no self.conditionsFile is set
        """
        self.refreshConditions()
        conditions = self.conditions # list of dict
        if self.conditionsFile:
            # get name + dir, like BART/trialTypes.xlsx
            fileName = os.path.abspath(self.conditionsFile)
            fileName = fileName.rsplit(os.path.sep,2)[1:]
            fileName = os.path.join(*fileName)
            if fileName.endswith('.pkl'):
                # edit existing .pkl file, loading from file
                gridGUI = DlgConditions(fileName=self.conditionsFile,
                                            parent=self, title=fileName)
            else:
                # preview existing .csv or .xlsx file that has already been loaded -> conditions
                # better to reload file, get fieldOrder as well
                gridGUI = DlgConditions(conditions, parent=self,
                                        title=fileName, fixed=True)
        else: # edit new empty .pkl file
            gridGUI = DlgConditions(parent=self)
            # should not check return value, its meaningless
            if gridGUI.OK:
                self.conditions = gridGUI.asConditions()
                if hasattr(gridGUI, 'fileName'):
                    self.conditionsFile = gridGUI.fileName
        self.currentHandler.params['conditionsFile'].val = self.conditionsFile
        if self.conditionsFile: # as set via DlgConditions
            valCtrl = self.constantsCtrls['conditionsFile'].valueCtrl
            valCtrl.Clear()
            valCtrl.WriteText(getAbbrev(self.conditionsFile))
        # still need to do namespace and internal updates (see end of onBrowseTrialsFile)

    def setCtrls(self, ctrlType):
        #create a list of ctrls to hide
        toHide = self.currentCtrls.values()
        if len(toHide)==0:
            toHide.extend(self.staircaseCtrls.values())
            toHide.extend(self.multiStairCtrls.values())
            toHide.extend(self.constantsCtrls.values())
        #choose the ctrls to show/hide
        if ctrlType=='staircase':
            self.currentHandler = self.stairHandler
            toShow = self.staircaseCtrls
        elif ctrlType=='interleaved staircase':
            self.currentHandler = self.multiStairHandler
            toShow = self.multiStairCtrls
        else:
            self.currentHandler = self.trialHandler
            toShow = self.constantsCtrls
        #hide them
        for ctrls in toHide:
            if ctrls.nameCtrl: ctrls.nameCtrl.Hide()
            if ctrls.valueCtrl: ctrls.valueCtrl.Hide()
            if ctrls.browseCtrl: ctrls.browseCtrl.Hide()
        #show them
        for paramName in toShow.keys():
            ctrls=toShow[paramName]
            if ctrls.nameCtrl: ctrls.nameCtrl.Show()
            if ctrls.valueCtrl: ctrls.valueCtrl.Show()
            if ctrls.browseCtrl: ctrls.browseCtrl.Show()
        self.currentCtrls=toShow
        self.ctrlSizer.Layout()
        self.Fit()
        self.Refresh()
    def onTypeChanged(self, evt=None):
        newType = evt.GetString()
        if newType==self.currentType:
            return
        self.setCtrls(newType)
    def onBrowseTrialsFile(self, event):
        self.conditionsFileOrig = self.conditionsFile
        self.conditionsOrig = self.conditions
        expFolder,expName = os.path.split(self.frame.filename)
        dlg = wx.FileDialog(self, message="Open file ...", style=wx.OPEN,
                            defaultDir=expFolder)
        if dlg.ShowModal() == wx.ID_OK:
            newFullPath = dlg.GetPath()
            if self.conditionsFile:
                oldFullPath = os.path.abspath(os.path.join(expFolder, self.conditionsFile))
                isSameFilePathAndName = (newFullPath==oldFullPath)
            else:
                isSameFilePathAndName = False
            newPath = _relpath(newFullPath, expFolder)
            self.conditionsFile = newPath
            try:
                self.conditions, self.condNamesInFile = data.importConditions(dlg.GetPath(),
                                                        returnFieldNames=True)
            except ImportError, msg:
                msg = str(msg)
                if msg.startswith('Could not open'):
                    self.constantsCtrls['conditions'].setValue(msg)
                    log.error('Could not open as a conditions file.')
                else:
                    self.constantsCtrls['conditions'].setValue(
                        'Badly formed condition name(s) in file:\n'+msg.replace(':','\n'))
                    log.error('Rejected bad condition name in conditions file: %s' % msg.split(':')[0])
                self.conditionsFile = self.conditionsFileOrig
                self.conditions = self.conditionsOrig
                logging.error('Rejected bad condition name in conditions file: %s' % str(msg).split(':')[0])
                return

            duplCondNames = []
            if len(self.condNamesInFile):
                for condName in self.condNamesInFile:
                    if self.exp.namespace.exists(condName):
                        duplCondNames.append(condName)
            duplCondNamesStr = ' '.join(duplCondNames)[:42]
            if len(duplCondNamesStr)==42:
                duplCondNamesStr = duplCondNamesStr[:39]+'...'
            if len(duplCondNames):
                if isSameFilePathAndName:
                    logging.info('Assuming reloading file: same filename and duplicate condition names in file: %s' % self.conditionsFile)
                else:
                    self.constantsCtrls['conditionsFile'].setValue(getAbbrev(newPath))
                    self.constantsCtrls['conditions'].setValue(
                        'Warning: Condition names conflict with existing:\n['+duplCondNamesStr+
                        ']\nProceed anyway? (= safe if these are in old file)')
                    logging.warning('Duplicate condition names, different conditions file: %s' % duplCondNamesStr)
            # stash condition names but don't add to namespace yet, user can still cancel
            self.duplCondNames = duplCondNames # add after self.show() in __init__

            if 'conditionsFile' in self.currentCtrls.keys() and not duplCondNames:
                self.constantsCtrls['conditionsFile'].setValue(getAbbrev(newPath))
                self.constantsCtrls['conditions'].setValue(self.getTrialsSummary(self.conditions))

    def getParams(self):
        """Retrieves data and re-inserts it into the handler and returns those handler params
        """
        #get data from input fields
        for fieldName in self.currentHandler.params.keys():
            if fieldName=='endPoints':continue#this was deprecated in v1.62.00
            param=self.currentHandler.params[fieldName]
            if fieldName in ['conditionsFile']:
                param.val=self.conditionsFile#not the value from ctrl - that was abbreviated
                # see onOK() for partial handling = check for '...'
            else:#most other fields
                ctrls = self.currentCtrls[fieldName]#the various dlg ctrls for this param
                param.val = ctrls.getValue()#from _baseParamsDlg (handles diff control types)
                if ctrls.typeCtrl: param.valType = ctrls.getType()
                if ctrls.updateCtrl: param.updates = ctrls.getUpdates()
        return self.currentHandler.params
    def refreshConditions(self):
        """user might have manually edited the conditionsFile name, which in turn
        affects self.conditions and namespace. its harder to handle changes to
        long names that have been abbrev()'d, so skip them (names containing '...').
        """
        val = self.currentCtrls['conditionsFile'].valueCtrl.GetValue()
        if val.find('...')==-1 and self.conditionsFile != val:
            self.conditionsFile = val
            if self.conditions:
                self.exp.namespace.remove(self.conditions[0].keys())
            if os.path.isfile(self.conditionsFile):
                try:
                    self.conditions = data.importConditions(self.conditionsFile)
                    self.constantsCtrls['conditions'].setValue(self.getTrialsSummary(self.conditions))
                except ImportError, msg:
                    self.constantsCtrls['conditions'].setValue(
                        'Badly formed condition name(s) in file:\n'+str(msg).replace(':','\n')+
                        '.\nNeed to be legal as var name; edit file, try again.')
                    self.conditions = ''
                    logging.error('Rejected bad condition name in conditions file: %s' % str(msg).split(':')[0])
            else:
                self.conditions = None
                self.constantsCtrls['conditions'].setValue("No parameters set (conditionsFile not found)")
        else:
            logging.debug('DlgLoop: could not determine if a condition filename was edited')
            #self.constantsCtrls['conditions'] could be misleading at this point
    def onOK(self, event=None):
        # intercept OK in case user deletes or edits the filename manually
        if 'conditionsFile' in self.currentCtrls.keys():
            self.refreshConditions()
        event.Skip() # do the OK button press

class DlgComponentProperties(_BaseParamsDlg):
    def __init__(self,frame,title,params,order,
            helpUrl=None, suppressTitles=True,
            pos=wx.DefaultPosition, size=wx.DefaultSize,
            style=wx.DEFAULT_DIALOG_STYLE|wx.DIALOG_NO_PARENT,
            editing=False):
        style=style|wx.RESIZE_BORDER
        _BaseParamsDlg.__init__(self,frame,title,params,order,
                                helpUrl=helpUrl,
                                pos=pos,size=size,style=style,
                                editing=editing)
        self.frame=frame
        self.app=frame.app
        self.dpi=self.app.dpi

        #for input devices:
        if 'storeCorrect' in self.params:
            self.onStoreCorrectChange(event=None)#do this just to set the initial values to be
            self.Bind(wx.EVT_CHECKBOX, self.onStoreCorrectChange, self.paramCtrls['storeCorrect'].valueCtrl)

        #for all components
        self.show()
        if self.OK:
            self.params = self.getParams()#get new vals from dlg
        self.Destroy()
    def onStoreCorrectChange(self,event=None):
        """store correct has been checked/unchecked. Show or hide the correctAns field accordingly"""
        if self.paramCtrls['storeCorrect'].valueCtrl.GetValue():
            self.paramCtrls['correctAns'].valueCtrl.Show()
            self.paramCtrls['correctAns'].nameCtrl.Show()
            #self.paramCtrls['correctAns'].typeCtrl.Show()
            #self.paramCtrls['correctAns'].updateCtrl.Show()
        else:
            self.paramCtrls['correctAns'].valueCtrl.Hide()
            self.paramCtrls['correctAns'].nameCtrl.Hide()
            #self.paramCtrls['correctAns'].typeCtrl.Hide()
            #self.paramCtrls['correctAns'].updateCtrl.Hide()
        self.ctrlSizer.Layout()
        self.Fit()
        self.Refresh()

class DlgExperimentProperties(_BaseParamsDlg):
    def __init__(self,frame,title,params,order,suppressTitles=False,
            pos=wx.DefaultPosition, size=wx.DefaultSize,helpUrl=None,
            style=wx.DEFAULT_DIALOG_STYLE|wx.DIALOG_NO_PARENT):
        style=style|wx.RESIZE_BORDER
        _BaseParamsDlg.__init__(self,frame,'Experiment Settings',params,order,
                                pos=pos,size=size,style=style,helpUrl=helpUrl)
        self.frame=frame
        self.app=frame.app
        self.dpi=self.app.dpi

        #for input devices:
        self.onFullScrChange(event=None)#do this just to set the initial values to be
        self.Bind(wx.EVT_CHECKBOX, self.onFullScrChange, self.paramCtrls['Full-screen window'].valueCtrl)

        #for all components
        self.show()
        if self.OK:
            self.params = self.getParams()#get new vals from dlg
        self.Destroy()

    def onFullScrChange(self,event=None):
        """store correct has been checked/unchecked. Show or hide the correctAns field accordingly"""
        if self.paramCtrls['Full-screen window'].valueCtrl.GetValue():
            #get screen size for requested display
            num_displays = wx.Display.GetCount()
            if int(self.paramCtrls['Screen'].valueCtrl.GetValue())>num_displays:
                logging.error("User requested non-existent screen")
            else:
                screenN=int(self.paramCtrls['Screen'].valueCtrl.GetValue())-1
            size=list(wx.Display(screenN).GetGeometry()[2:])
            #set vals and disable changes
            self.paramCtrls['Window size (pixels)'].valueCtrl.SetValue(unicode(size))
            self.paramCtrls['Window size (pixels)'].valueCtrl.Disable()
            self.paramCtrls['Window size (pixels)'].nameCtrl.Disable()
        else:
            self.paramCtrls['Window size (pixels)'].valueCtrl.Enable()
            self.paramCtrls['Window size (pixels)'].nameCtrl.Enable()
        self.ctrlSizer.Layout()
        self.Fit()
        self.Refresh()

    def show(self):
        """Adds an OK and cancel button, shows dialogue.

        This method returns wx.ID_OK (as from ShowModal), but also
        sets self.OK to be True or False
        """
        #add buttons for help, OK and Cancel
        self.mainSizer=wx.BoxSizer(wx.VERTICAL)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        if self.helpUrl!=None:
            helpBtn = wx.Button(self, wx.ID_HELP)
            helpBtn.SetHelpText("Get help about this component")
            helpBtn.Bind(wx.EVT_BUTTON, self.onHelp)
            buttons.Add(helpBtn, 0, wx.ALIGN_RIGHT|wx.ALL,border=3)
        self.OKbtn = wx.Button(self, wx.ID_OK, " OK ")
        self.OKbtn.SetDefault()
        buttons.Add(self.OKbtn, 0, wx.ALIGN_RIGHT|wx.ALL,border=3)
        CANCEL = wx.Button(self, wx.ID_CANCEL, " Cancel ")
        buttons.Add(CANCEL, 0, wx.ALIGN_RIGHT|wx.ALL,border=3)

        self.mainSizer.Add(self.ctrlSizer)
        self.mainSizer.Add(buttons, flag=wx.ALIGN_RIGHT)
        self.SetSizerAndFit(self.mainSizer)
        #do show and process return
        retVal = self.ShowModal()
        if retVal== wx.ID_OK: self.OK=True
        else:  self.OK=False
        return wx.ID_OK

class DlgConditions(wx.Dialog):
    """Given a file or conditions, present values in a grid; view, edit, save.

    Accepts file name, list of lists, or list-of-dict
    Designed around a conditionsFile, but potentially more general.

    Example usage: from builder.DlgLoopProperties.viewConditions()
    edit new empty .pkl file:
        gridGUI = builder.DlgConditions(parent=self) # create and present Dlg
    edit existing .pkl file, loading from file (also for .csv or .xlsx):
        gridGUI = builder.DlgConditions(fileName=self.conditionsFile,
                                    parent=self, title=fileName)
    preview existing .csv or .xlsx file that has already been loaded -> conditions:
        gridGUI = builder.DlgConditions(conditions, parent=self,
                                    title=fileName, fixed=True)

    To add columns, an instance of this class will instantiate a new instance
    having one more column. Doing so makes the return value from the first instance's
    showModal() meaningless. In order to update things like fileName and conditions,
    values are set in the parent, and should not be set based on showModal retVal.

    Author: Jeremy Gray, 2011
    """
    def __init__(self, grid=None, fileName=False, parent=None, title='',
            trim=True, fixed=False, hasHeader=True, gui=True, extraRows=0, extraCols=0,
            clean=True, pos=None, preview=True,
            _restore=None, size=wx.DefaultSize,
            style=wx.DEFAULT_DIALOG_STYLE|wx.DIALOG_NO_PARENT):
        self.parent = parent # gets the conditionsFile info
        if parent: self.helpUrl = self.parent.app.urls['builder.loops']
        # read data from file, if any:
        self.defaultFileName = 'conditions.pkl'
        self.newFile = True
        if _restore:
            self.newFile = _restore[0]
            self.fileName = _restore[1]
        if fileName:
            grid = self.load(fileName)
            if grid:
                self.fileName = fileName
                self.newFile = False
            if not title:
                f = os.path.abspath(fileName)
                f = f.rsplit(os.path.sep,2)[1:]
                f = os.path.join(*f) # eg, BART/trialTypes.xlsx
                title = f
        elif not grid:
            title = 'New (no file)'
        elif _restore:
            if not title:
                f = os.path.abspath(_restore[1])
                f = f.rsplit(os.path.sep,2)[1:]
                f = os.path.join(*f) # eg, BART/trialTypes.xlsx
                title = f
        elif not title:
            title = 'Conditions data (no file)'
        # if got here via addColumn:
        # convert from conditions dict format:
        if grid and type(grid) == list and type(grid[0]) == dict:
            conditions = grid[:]
            numCond, numParam = len(conditions), len(conditions[0])
            grid = [conditions[0].keys()]
            for i in xrange(numCond):
                row = conditions[i].values()
                grid.append(row)
            hasHeader=True # keys of a dict are the header
        # ensure a sensible grid, or provide a basic default:
        if not grid or not len(grid) or not len(grid[0]):
            grid = [[self.colName(0)], [u'']]
            hasHeader = True
            extraRows += 5
            extraCols += 3
        self.grid = grid # grid is list of lists
        self.fixed = bool(fixed)
        if self.fixed:
            extraRows = extraCols = 0
            trim = clean = confirm = False
        else:
            style = style|wx.RESIZE_BORDER
        self.pos = pos
        self.title = title
        try:
            self.madeApp = False
            wx.Dialog.__init__(self, None,-1,title,pos,size,style)
        except: # only needed during development?
            self.madeApp = True
            global app
            app = wx.PySimpleApp()
            wx.Dialog.__init__(self, None,-1,title,pos,size,style)
        self.trim = trim
        self.warning = '' # updated to warn about eg, trailing whitespace
        if hasHeader and not len(grid) > 1 and not self.fixed:
            self.grid.append([])
        self.clean = bool(clean)
        self.typeChoices = ['None', 'str', 'utf-8', 'int', 'long', 'float',
                            'bool', 'list', 'tuple', 'array']
        # make all rows have same # cols, extending as needed or requested:
        longest = max([len(r) for r in self.grid]) + extraCols
        for row in self.grid:
            for i in range(len(row),longest):
                row.append(u'') # None
        self.hasHeader = bool(hasHeader) # self.header <== row of input param name fields
        self.rows = min(len(self.grid), 30) # max 30 rows displayed
        self.cols = len(self.grid[0])
        extraRow = int(not self.fixed) # extra row for explicit type drop-down
        self.sizer = wx.FlexGridSizer(self.rows+extraRow, self.cols+1, # +1 for condition labels
                                      vgap=0, hgap=0)
        # set length of input box as the longest in the column (bounded):
        self.colSizes = []
        for x in range(self.cols):
            self.colSizes.append( max([4] +
                [len(unicode(self.grid[y][x])) for y in range(self.rows)]) )
        self.colSizes = map(lambda x: min(20, max(10, x+1)) * 8 + 30, self.colSizes)
        self.inputTypes = [] # explicit, as selected by user via type-selector
        self.inputFields = [] # values in fields
        self.data = []

        # make header label, if any:
        if self.hasHeader:
            rowLabel = wx.StaticText(self,-1,label='Params:', size=(6*9, 20))
            rowLabel.SetForegroundColour(darkblue)
            self.addRow(0, rowLabel=rowLabel)
        # make type-selector drop-down:
        if not self.fixed:
            if sys.platform == 'darwin':
                self.SetWindowVariant(variant=wx.WINDOW_VARIANT_SMALL)
            labelBox = wx.BoxSizer(wx.VERTICAL)
            tx = wx.StaticText(self,-1,label='type:', size=(5*9,20))
            tx.SetForegroundColour(darkgrey)
            labelBox.Add(tx,1,flag=wx.ALIGN_RIGHT)
            labelBox.AddSpacer(5) # vertical
            self.sizer.Add(labelBox,1,flag=wx.ALIGN_RIGHT)
            row = int(self.hasHeader) # row to use for type inference
            for col in range(self.cols):
                # make each selector:
                typeOpt = wx.Choice(self, choices=self.typeChoices)
                # set it to best guess about the column's type:
                firstType = str(type(self.grid[row][col])).split("'",2)[1]
                if firstType=='numpy.ndarray':
                    firstType = 'array'
                if firstType=='unicode':
                    firstType = 'utf-8'
                typeOpt.SetStringSelection(str(firstType))
                self.inputTypes.append(typeOpt)
                self.sizer.Add(typeOpt, 1)
            if sys.platform == 'darwin':
                self.SetWindowVariant(variant=wx.WINDOW_VARIANT_NORMAL)
        # stash implicit types for setType:
        self.types = [] # implicit types
        row = int(self.hasHeader) # which row to use for type inference
        for col in range(self.cols):
            firstType = str(type(self.grid[row][col])).split("'")[1]
            self.types.append(firstType)
        # add normal row:
        for row in range(int(self.hasHeader), self.rows):
            self.addRow(row)
        for r in range(extraRows):
            self.grid.append([ u'' for i in range(self.cols)])
            self.rows = len(self.grid)
            self.addRow(self.rows-1)
        # show the GUI:
        if gui:
            self.show()
            self.Destroy()
        if self.madeApp:
            del(self, app)

    def colName(self, c, prefix='param_'):
        # generates 702 excel-style column names, A ... ZZ, with prefix
        abc = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' # for A, ..., Z
        aabb = [''] + [ch for ch in abc] # for Ax, ..., Zx
        return prefix + aabb[c//26] + abc[c%26]
    def addRow(self, row, rowLabel=None):
        """Add one row of info, either header (col names) or normal data

        Adds items sequentially; FlexGridSizer moves to next row automatically
        """
        labelBox = wx.BoxSizer(wx.HORIZONTAL)
        if not rowLabel:
            if sys.platform == 'darwin':
                self.SetWindowVariant(variant=wx.WINDOW_VARIANT_SMALL)
            label = 'cond %s:'%str(row+1-int(self.hasHeader)).zfill(2)
            rowLabel = wx.StaticText(self, -1, label=label)
            rowLabel.SetForegroundColour(darkgrey)
            if sys.platform == 'darwin':
                self.SetWindowVariant(variant=wx.WINDOW_VARIANT_NORMAL)
        labelBox.Add(rowLabel, 1, flag=wx.ALIGN_RIGHT|wx.ALIGN_BOTTOM)
        self.sizer.Add(labelBox, 1, flag=wx.ALIGN_CENTER)
        lastRow = []
        for col in range(self.cols):
            # get the item, as unicode for display purposes:
            if len(unicode(self.grid[row][col])): # want 0, for example
                item = unicode(self.grid[row][col])
            else:
                item = u''
            # make a textbox:
            field = ExpandoTextCtrl(self, -1, item, size=(self.colSizes[col],20))
            field.Bind(EVT_ETC_LAYOUT_NEEDED, self.onNeedsResize)
            field.SetMaxHeight(100) # ~ 5 lines
            if self.hasHeader and row==0:
                # add a default column name (header) if none provided
                header = self.grid[0]
                if item.strip() == '':
                    c = col
                    while self.colName(c) in header:
                        c += 1
                    field.SetValue(self.colName(c))
                field.SetForegroundColour(darkblue) #dark blue
                if not _valid_var_re.match(field.GetValue()): #or (self.parent and
                            #self.parent.exp.namespace.exists(field.GetValue()) ):
                            # was always red when preview .xlsx file -- in namespace already is fine
                    if self.fixed:
                        field.SetForegroundColour("Red")
                field.SetToolTip(wx.ToolTip('Should be legal as a variable name (alphanumeric)'))
                field.Bind(wx.EVT_TEXT, self.checkName)
            elif self.fixed:
                field.SetForegroundColour(darkgrey)
                field.SetBackgroundColour(white)

            # warn about whitespace unless will be auto-removed. invisible, probably spurious:
            if (self.fixed or not self.clean) and item != item.lstrip().strip():
                field.SetForegroundColour('Red')
                self.warning = 'extra white-space' # also used in show()
                field.SetToolTip(wx.ToolTip(self.warning))
            if self.fixed:
                field.Disable()
            lastRow.append(field)
            self.sizer.Add(field, 1)
        self.inputFields.append(lastRow)
        if self.hasHeader and row==0:
            self.header = lastRow
    def checkName(self, event=None, name=None):
        """check param name (missing, namespace conflict, legal var name)
        disable save, save-as if bad name
        """
        if self.parent:
            if event:
                msg, enable = self.parent._checkName(event=event)
            else:
                msg, enable = self.parent._checkName(name=name)
        else:
            if (name and not _valid_var_re.match(name)
                or not _valid_var_re.match(event.GetString()) ):
                msg, enable = "Name must be alpha-numeric or _, no spaces", False
            else:
                msg, enable = "", True
        self.tmpMsg.SetLabel(msg)
        if enable:
            self.OKbtn.Enable()
            self.SAVEAS.Enable()
        else:
            self.OKbtn.Disable()
            self.SAVEAS.Disable()
    def userAddRow(self, event=None):
        """handle user request to add another row: just add to the FlexGridSizer
        """
        self.grid.append([ u''] * self.cols)
        self.rows = len(self.grid)
        self.addRow(self.rows-1)
        self.tmpMsg.SetLabel('')
        self.onNeedsResize()
    def userAddCol(self, event=None):
        """adds a column by recreating the Dlg with a wider size one more column
        relaunch loses the retVal from OK, so use parent.fileName not OK for exit status
        """
        self.relaunch(kwargs={'extraCols':1, 'title':self.title})
    def relaunch(self, kwargs={}):
        self.trim = False # avoid removing blank rows / cols that user has added
        self.getData(True)
        currentData = self.data[:]
        # launch new Dlg, but only after bail out of current one:
        if hasattr(self, 'fileName'): fname = self.fileName
        else: fname = None
        wx.CallAfter(DlgConditions, currentData, _restore=(self.newFile,fname),
                     parent=self.parent, **kwargs)
        # bail from current Dlg:
        self.EndModal(wx.ID_OK) # retVal here, first one goes to Builder, ignore
        #self.Destroy() # -> PyDeadObjectError, so already handled hopefully
    def getData(self, typeSelected=False):
        """gets data from inputFields (unicode), converts to desired type
        """
        if self.fixed:
            self.data = self.grid
            return
        elif typeSelected: # get user-selected explicit types of the columns
            self.types = []
            for col in range(self.cols):
                selected = self.inputTypes[col].GetCurrentSelection()
                self.types.append(self.typeChoices[selected])
        # mark empty columns for later removal:
        if self.trim:
            start = int(self.hasHeader) # name is not empty, so ignore
            for col in range(self.cols):
                if not ''.join([self.inputFields[row][col].GetValue()
                                for row in range(start, self.rows)]):
                    self.types[col] = 'None' # col will be removed below
        # get the data:
        self.data = []
        for row in range(self.rows):
            lastRow = []
            # remove empty rows
            if self.trim and not ''.join([self.inputFields[row][col].GetValue()
                                          for col in range(self.cols)]):
                continue
            for col in range(self.cols):
                thisType = self.types[col]
                # trim 'None' columns, including header name:
                if self.trim and thisType in ['None']:
                    continue
                thisVal = self.inputFields[row][col].GetValue()
                if self.clean:
                    thisVal = thisVal.lstrip().strip()
                if thisVal:# and thisType in ['list', 'tuple', 'array']:
                    while len(thisVal) and thisVal[-1] in "]), ":
                        thisVal = thisVal[:-1]
                    while len(thisVal) and thisVal[0] in "[(, ":
                        thisVal = thisVal[1:]

                if thisType not in ['str', 'utf-8']:
                    thisVal = thisVal.replace('\n', '')
                else:
                    thisVal = repr(thisVal) # handles quoting ', ", ''' etc
                # convert to requested type:
                try:
                    if self.hasHeader and row==0:
                        lastRow.append(str(self.inputFields[row][col].GetValue())) # header always str
                    elif thisType in ['float','int', 'long']:
                        exec("lastRow.append("+thisType+'('+thisVal+"))")
                    elif thisType in ['list']:
                        thisVal = thisVal.lstrip('[').strip(']')
                        exec("lastRow.append("+thisType+'(['+thisVal+"]))")
                    elif thisType in ['tuple']:
                        thisVal = thisVal.lstrip('(').strip(')')
                        if thisVal:
                            exec("lastRow.append(("+thisVal.strip(',')+",))")
                        else:
                            lastRow.append(tuple(()))
                    elif thisType in ['array']:
                        thisVal = thisVal.lstrip('[').strip(']')
                        exec("lastRow.append(numpy.array"+'("['+thisVal+']"))')
                    elif thisType in ['utf-8', 'bool']:
                        if thisType=='utf-8': thisType='unicode'
                        exec("lastRow.append("+thisType+'('+thisVal+'))')
                    elif thisType in ['str']:
                        exec("lastRow.append(str("+thisVal+"))")
                    elif thisType in ['file']:
                        exec("lastRow.append(repr("+thisVal+"))")
                    else: #if thisType in ['NoneType']:
                        #assert False, 'programer error, unknown type: '+thisType
                        exec("lastRow.append("+unicode(thisVal)+')')
                except ValueError, msg:
                    print 'ValueError:', msg, '; using unicode'
                    exec("lastRow.append("+unicode(thisVal)+')')
                except NameError, msg:
                    print 'NameError:', msg, '; using unicode'
                    exec("lastRow.append("+repr(thisVal)+')')
            self.data.append(lastRow)
        if self.trim:
            # the corresponding data have already been removed
            while 'None' in self.types:
                self.types.remove('None')
        return self.data[:]

    def preview(self,event=None):
        self.getData(typeSelected=True)
        previewData = self.data[:] # in theory, self.data is also ok, because fixed
            # is supposed to never change anything, but bugs would be very subtle
        DlgConditions(previewData, parent=self.parent, title='PREVIEW', fixed=True)
    def onNeedsResize(self, event=None):
        self.SetSizerAndFit(self.border) # do outer-most sizer
        if self.pos==None: self.Center()
    def show(self):
        """called internally; to display, pass gui=True to init
        """
        # put things inside a border:
        self.border = wx.FlexGridSizer(2,1) # data matrix on top, buttons below
        self.border.Add(self.sizer, proportion=1, flag=wx.ALL|wx.EXPAND, border=8)

        # add a message area, buttons:
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        if sys.platform == 'darwin':
            self.SetWindowVariant(variant=wx.WINDOW_VARIANT_SMALL)
        if not self.fixed:
            # placeholder for possible messages / warnings:
            self.tmpMsg = wx.StaticText(self, -1, label='', size=(350,15), style=wx.ALIGN_RIGHT)
            self.tmpMsg.SetForegroundColour('Red')
            if self.warning:
                self.tmpMsg.SetLabel(self.warning)
            buttons.Add(self.tmpMsg, flag=wx.ALIGN_CENTER)
            buttons.AddSpacer(8)
            self.border.Add(buttons,1,flag=wx.BOTTOM|wx.ALIGN_CENTER, border=8)
            buttons = wx.BoxSizer(wx.HORIZONTAL)
            size=(60,15)
            if sys.platform.startswith('linux'):
                size=(75, 30)
            ADDROW = wx.Button(self, -1, "+cond.", size=size) # good size for mac, SMALL
            ADDROW.SetToolTip(wx.ToolTip('Add a condition (row); to delete a condition, delete all of its values.'))
            ADDROW.Bind(wx.EVT_BUTTON, self.userAddRow)
            buttons.Add(ADDROW)
            buttons.AddSpacer(4)
            ADDCOL = wx.Button(self, -1, "+param", size=size)
            ADDCOL.SetToolTip(wx.ToolTip('Add a parameter (column); to delete a param, set its type to None, or delete all of its values.'))
            ADDCOL.Bind(wx.EVT_BUTTON, self.userAddCol)
            buttons.Add(ADDCOL)
            buttons.AddSpacer(4)
            PREVIEW = wx.Button(self, -1, "Preview")
            PREVIEW.SetToolTip(wx.ToolTip("Show all values as they would appear after saving to a file, without actually saving anything."))
            PREVIEW.Bind(wx.EVT_BUTTON, self.preview)
            buttons.Add(PREVIEW)
            buttons.AddSpacer(4)
            self.SAVEAS = wx.Button(self, wx.SAVE, "Save as")
            self.SAVEAS.Bind(wx.EVT_BUTTON, self.saveAs)
            buttons.Add(self.SAVEAS)
            buttons.AddSpacer(8)
            self.border.Add(buttons,1,flag=wx.BOTTOM|wx.ALIGN_RIGHT, border=8)
        if sys.platform == 'darwin':
            self.SetWindowVariant(variant=wx.WINDOW_VARIANT_NORMAL)
        buttons = wx.StdDialogButtonSizer()
        #help button if we know the url
        if self.helpUrl and not self.fixed:
            helpBtn = wx.Button(self, wx.ID_HELP)
            helpBtn.SetToolTip(wx.ToolTip("Go to online help"))
            helpBtn.Bind(wx.EVT_BUTTON, self.onHelp)
            buttons.Add(helpBtn, wx.ALIGN_LEFT|wx.ALL)
            buttons.AddSpacer(12)
        self.OKbtn = wx.Button(self, wx.ID_OK, " OK ")
        if not self.fixed:
            self.OKbtn.SetToolTip(wx.ToolTip('Save and exit'))
        self.OKbtn.Bind(wx.EVT_BUTTON, self.onOK)
        self.OKbtn.SetDefault()
        buttons.Add(self.OKbtn)
        if not self.fixed:
            buttons.AddSpacer(4)
            CANCEL = wx.Button(self, wx.ID_CANCEL, " Cancel ")
            CANCEL.SetToolTip(wx.ToolTip('Exit, discard any edits'))
            buttons.Add(CANCEL)
        buttons.AddSpacer(8)
        buttons.Realize()
        self.border.Add(buttons,1,flag=wx.BOTTOM|wx.ALIGN_RIGHT, border=8)

        # finally, its show time:
        self.SetSizerAndFit(self.border)
        if self.pos==None: self.Center()
        if self.ShowModal() == wx.ID_OK:
            self.getData(typeSelected=True) # set self.data and self.types, from fields
            self.OK = True
        else:
            self.data = self.types = None
            self.OK = False
        self.Destroy()
    def onOK(self, event=None):
        if not self.fixed:
            if not self.save():
                return # disallow OK if bad param names
        event.Skip() # handle the OK button event
    def saveAs(self, event=None):
        """save, but allow user to give a new name
        """
        self.newFile = True # trigger query for fileName
        self.save()
        self.relaunch() # to update fileName in title
    def save(self, event=None):
        """save header + row x col data to a pickle file
        """
        self.getData(True) # update self.data
        adjustedNames = False
        for i, paramName in enumerate(self.data[0]):
            newName = paramName
            # ensure its legal as a var name, including namespace check:
            if self.parent:
                msg, enable = self.parent._checkName(name=paramName)
                if msg: # msg not empty means a namespace issue
                    newName = self.parent.exp.namespace.makeValid(paramName, prefix='param')
                    adjustedNames = True
            elif not _valid_var_re.match(paramName):
                msg, enable = "Name must be alpha-numeric or _, no spaces", False
                newName = _nonalphanumeric_re.sub('_', newName)
                adjustedNames = True
            else:
                msg, enable = "", True
            # try to ensure its unique:
            while newName in self.data[0][:i]:
                adjustedNames = True
                newName += 'x' # unlikely to create a namespace conflict, but could happen
            self.data[0][i] = newName
            self.header[i].SetValue(newName) # displayed value
        if adjustedNames:
            self.tmpMsg.SetLabel('Param name(s) adjusted to be legal. Look ok?')
            return False
        if hasattr(self, 'fileName') and self.fileName:
            fname = self.fileName
        else:
            self.newFile = True
            fname = self.defaultFileName
        if self.newFile or not os.path.isfile(fname):
            fullPath = gui.fileSaveDlg(initFilePath=os.path.split(fname)[0],
                initFileName=os.path.basename(fname),
                        allowed="Pickle files *.pkl")
        else:
            fullPath = fname
        if fullPath: # None if user canceled
            if not fullPath.endswith('.pkl'):
                fullPath += '.pkl'
            f = open(fullPath, 'w')
            cPickle.dump(self.data, f)
            f.close()
            self.fileName = fullPath
            self.newFile = False
            # ack, sometimes might want relative path
            if self.parent:
                self.parent.conditionsFile = fullPath
        return True
    def load(self, fileName=''):
        """read and return header + row x col data from a pickle file
        """
        if not fileName:
            fileName = self.defaultFileName
        if not os.path.isfile(fileName):
            fullPathList = gui.fileOpenDlg(tryFileName=os.path.basename(fileName),
                            allowed="All files (*.*)|*.*")
            if fullPathList:
                fileName = fullPathList[0] # wx.MULTIPLE -> list
        if os.path.isfile(fileName) and fileName.endswith('.pkl'):
            f = open(fileName)
            contents = cPickle.load(f)
            f.close()
            if self.parent:
                self.parent.conditionsFile = fileName
            return contents
        elif not os.path.isfile(fileName):
            print 'file %s not found' % fileName
        else:
            print 'only .pkl supported at the moment'
    def asConditions(self):
        """converts self.data into self.conditions for TrialHandler, returns conditions
        """
        if not self.data or not self.hasHeader:
            if hasattr(self, 'conditions') and self.conditions:
                return self.conditions
            return
        self.conditions = []
        keyList = self.data[0] # header = keys of dict
        for row in self.data[1:]:
            condition = {}
            for col, key in enumerate(keyList):
                condition[key] = row[col]
            self.conditions.append(condition)
        return self.conditions
    def onHelp(self, event=None):
        """similar to self.app.followLink() to self.helpUrl, but only use url
        """
        wx.LaunchDefaultBrowser(self.helpUrl)

class BuilderFrame(wx.Frame):
    def __init__(self, parent, id=-1, title='PsychoPy (Experiment Builder)',
                 pos=wx.DefaultPosition, fileName=None,frameData=None,
                 style=wx.DEFAULT_FRAME_STYLE, app=None):

        self.app=app
        self.dpi=self.app.dpi
        self.appData = self.app.prefs.appData['builder']#things the user doesn't set like winsize etc
        self.prefs = self.app.prefs.builder#things about the coder that get set
        self.appPrefs = self.app.prefs.app
        self.paths = self.app.prefs.paths
        self.IDs = self.app.IDs
        self.frameType='builder'
        self.filename = fileName

        if fileName in self.appData['frames'].keys():
            self.frameData = self.appData['frames'][fileName]
        else:#work out a new frame size/location
            dispW,dispH = self.app.getPrimaryDisplaySize()
            default=self.appData['defaultFrame']
            default['winW'], default['winH'],  = int(dispW*0.75), int(dispH*0.75)
            if default['winX']+default['winW']>dispW:
                default['winX']=5
            if default['winY']+default['winH']>dispH:
                default['winY']=5
            self.frameData = dict(self.appData['defaultFrame'])#take a copy
            #increment default for next frame
            default['winX']+=10
            default['winY']+=10

        if self.frameData['winH']==0 or self.frameData['winW']==0:#we didn't have the key or the win was minimized/invalid

            self.frameData['winX'], self.frameData['winY'] = (0,0)
            usingDefaultSize=True
        else:
            usingDefaultSize=False
        wx.Frame.__init__(self, parent=parent, id=id, title=title,
                            pos=(int(self.frameData['winX']), int(self.frameData['winY'])),
                            size=(int(self.frameData['winW']),int(self.frameData['winH'])),
                            style=style)

        self.panel = wx.Panel(self)
        #create icon
        if sys.platform=='darwin':
            pass#doesn't work and not necessary - handled by application bundle
        else:
            iconFile = os.path.join(self.paths['resources'], 'psychopy.ico')
            if os.path.isfile(iconFile):
                self.SetIcon(wx.Icon(iconFile, wx.BITMAP_TYPE_ICO))

        # create our panels
        self.flowPanel=FlowPanel(frame=self)
        self.routinePanel=RoutinesNotebook(self)
        self.componentButtons=ComponentsPanel(self)
        #menus and toolbars
        self.makeToolbar()
        self.makeMenus()
        self.CreateStatusBar()
        self.SetStatusText("")

        #
        self.stdoutOrig = sys.stdout
        self.stderrOrig = sys.stderr
        self.stdoutFrame=stdOutRich.StdOutFrame(parent=self, app=self.app, size=(700,300))

        #setup a default exp
        if fileName!=None and os.path.isfile(fileName):
            self.fileOpen(filename=fileName, closeCurrent=False)
        else:
            self.lastSavedCopy=None
            self.fileNew(closeCurrent=False)#don't try to close before opening

        #control the panes using aui manager
        self._mgr = wx.aui.AuiManager(self)
        if self.prefs['topFlow']:
            self._mgr.AddPane(self.flowPanel,
                              wx.aui.AuiPaneInfo().
                              Name("Flow").Caption("Flow").BestSize((8*self.dpi,2*self.dpi)).
                              RightDockable(True).LeftDockable(True).CloseButton(False).
                              Top())
            self._mgr.AddPane(self.componentButtons, wx.aui.AuiPaneInfo().
                              Name("Components").Caption("Components").
                              RightDockable(True).LeftDockable(True).CloseButton(False).
                              Left())
            self._mgr.AddPane(self.routinePanel, wx.aui.AuiPaneInfo().
                              Name("Routines").Caption("Routines").
                              CenterPane(). #'center panes' expand to fill space
                              CloseButton(False).MaximizeButton(True))
        else:
            self._mgr.AddPane(self.routinePanel, wx.aui.AuiPaneInfo().
                              Name("Routines").Caption("Routines").
                              CenterPane(). #'center panes' expand to fill space
                              CloseButton(False).MaximizeButton(True))
            self._mgr.AddPane(self.componentButtons, wx.aui.AuiPaneInfo().
                              Name("Components").Caption("Components").
                              RightDockable(True).LeftDockable(True).CloseButton(False).
                              Right())
            self._mgr.AddPane(self.flowPanel,
                              wx.aui.AuiPaneInfo().
                              Name("Flow").Caption("Flow").BestSize((8*self.dpi,2*self.dpi)).
                              RightDockable(True).LeftDockable(True).CloseButton(False).
                              Bottom())
        #tell the manager to 'commit' all the changes just made
        self._mgr.Update()
        #self.SetSizer(self.mainSizer)#not necessary for aui type controls
        if self.frameData['auiPerspective']:
            self._mgr.LoadPerspective(self.frameData['auiPerspective'])
        self.SetMinSize(wx.Size(600, 400)) #min size for the whole window
        self.SetSize((int(self.frameData['winW']),int(self.frameData['winH'])))
        self.SendSizeEvent()
        self._mgr.Update()

        #self.SetAutoLayout(True)
        self.Bind(wx.EVT_CLOSE, self.closeFrame)
        self.Bind(wx.EVT_END_PROCESS, self.onProcessEnded)
    def makeToolbar(self):
        #---toolbar---#000000#FFFFFF----------------------------------------------
        self.toolbar = self.CreateToolBar( (wx.TB_HORIZONTAL
            | wx.NO_BORDER
            | wx.TB_FLAT))

        if sys.platform=='win32' or sys.platform.startswith('linux') or float(wx.version()[:3]) >= 2.8:
            if self.appPrefs['largeIcons']: toolbarSize=32
            else: toolbarSize=16
        else:
            toolbarSize=32 #size 16 doesn't work on mac wx; does work with wx.version() == '2.8.7.1 (mac-unicode)'
        self.toolbar.SetToolBitmapSize((toolbarSize,toolbarSize))
        self.toolbar.SetToolBitmapSize((toolbarSize,toolbarSize))
        new_bmp = wx.Bitmap(os.path.join(self.app.prefs.paths['resources'], 'filenew%i.png' %toolbarSize), wx.BITMAP_TYPE_PNG)
        open_bmp = wx.Bitmap(os.path.join(self.app.prefs.paths['resources'], 'fileopen%i.png' %toolbarSize), wx.BITMAP_TYPE_PNG)
        save_bmp = wx.Bitmap(os.path.join(self.app.prefs.paths['resources'], 'filesave%i.png' %toolbarSize), wx.BITMAP_TYPE_PNG)
        saveAs_bmp = wx.Bitmap(os.path.join(self.app.prefs.paths['resources'], 'filesaveas%i.png' %toolbarSize), wx.BITMAP_TYPE_PNG)
        undo_bmp = wx.Bitmap(os.path.join(self.app.prefs.paths['resources'], 'undo%i.png' %toolbarSize),wx.BITMAP_TYPE_PNG)
        redo_bmp = wx.Bitmap(os.path.join(self.app.prefs.paths['resources'], 'redo%i.png' %toolbarSize),wx.BITMAP_TYPE_PNG)
        stop_bmp = wx.Bitmap(os.path.join(self.app.prefs.paths['resources'], 'stop%i.png' %toolbarSize),wx.BITMAP_TYPE_PNG)
        run_bmp = wx.Bitmap(os.path.join(self.app.prefs.paths['resources'], 'run%i.png' %toolbarSize),wx.BITMAP_TYPE_PNG)
        compile_bmp = wx.Bitmap(os.path.join(self.app.prefs.paths['resources'], 'compile%i.png' %toolbarSize),wx.BITMAP_TYPE_PNG)
        settings_bmp = wx.Bitmap(os.path.join(self.app.prefs.paths['resources'], 'settingsExp%i.png' %toolbarSize), wx.BITMAP_TYPE_PNG)
        preferences_bmp = wx.Bitmap(os.path.join(self.app.prefs.paths['resources'], 'preferences%i.png' %toolbarSize), wx.BITMAP_TYPE_PNG)
        monitors_bmp = wx.Bitmap(os.path.join(self.app.prefs.paths['resources'], 'monitors%i.png' %toolbarSize), wx.BITMAP_TYPE_PNG)
        #colorpicker_bmp = wx.Bitmap(os.path.join(self.app.prefs.paths['resources'], 'color%i.png' %toolbarSize), wx.BITMAP_TYPE_PNG)

        ctrlKey = 'Ctrl+'  # show key-bindings in tool-tips in an OS-dependent way
        if sys.platform == 'darwin': ctrlKey = 'Cmd+'
        self.toolbar.AddSimpleTool(self.IDs.tbFileNew, new_bmp, ("New [%s]" %self.app.keys['new']).replace('Ctrl+', ctrlKey), "Create new python file")
        self.toolbar.Bind(wx.EVT_TOOL, self.app.newBuilderFrame, id=self.IDs.tbFileNew)
        self.toolbar.AddSimpleTool(self.IDs.tbFileOpen, open_bmp, ("Open [%s]" %self.app.keys['open']).replace('Ctrl+', ctrlKey), "Open an existing file")
        self.toolbar.Bind(wx.EVT_TOOL, self.fileOpen, id=self.IDs.tbFileOpen)
        self.toolbar.AddSimpleTool(self.IDs.tbFileSave, save_bmp, ("Save [%s]" %self.app.keys['save']).replace('Ctrl+', ctrlKey),  "Save current file")
        self.toolbar.EnableTool(self.IDs.tbFileSave, False)
        self.toolbar.Bind(wx.EVT_TOOL, self.fileSave, id=self.IDs.tbFileSave)
        self.toolbar.AddSimpleTool(self.IDs.tbFileSaveAs, saveAs_bmp, ("Save As... [%s]" %self.app.keys['saveAs']).replace('Ctrl+', ctrlKey), "Save current python file as...")
        self.toolbar.Bind(wx.EVT_TOOL, self.fileSaveAs, id=self.IDs.tbFileSaveAs)
        self.toolbar.AddSimpleTool(self.IDs.tbUndo, undo_bmp, ("Undo [%s]" %self.app.keys['undo']).replace('Ctrl+', ctrlKey), "Undo last action")
        self.toolbar.Bind(wx.EVT_TOOL, self.undo, id=self.IDs.tbUndo)
        self.toolbar.AddSimpleTool(self.IDs.tbRedo, redo_bmp, ("Redo [%s]" %self.app.keys['redo']).replace('Ctrl+', ctrlKey),  "Redo last action")
        self.toolbar.Bind(wx.EVT_TOOL, self.redo, id=self.IDs.tbRedo)
        self.toolbar.AddSeparator()
        self.toolbar.AddSeparator()
        self.toolbar.AddSimpleTool(self.IDs.tbPreferences, preferences_bmp, "Preferences",  "Application preferences")
        self.toolbar.Bind(wx.EVT_TOOL, self.app.showPrefs, id=self.IDs.tbPreferences)
        self.toolbar.AddSimpleTool(self.IDs.tbMonitorCenter, monitors_bmp, "Monitor Center",  "Monitor settings and calibration")
        self.toolbar.Bind(wx.EVT_TOOL, self.app.openMonitorCenter, id=self.IDs.tbMonitorCenter)
        #self.toolbar.AddSimpleTool(self.IDs.tbColorPicker, colorpicker_bmp, "Color Picker",  "Color Picker")
        #self.toolbar.Bind(wx.EVT_TOOL, self.app.colorPicker, id=self.IDs.tbColorPicker)
        self.toolbar.AddSeparator()
        self.toolbar.AddSeparator()
        self.toolbar.AddSimpleTool(self.IDs.tbExpSettings, settings_bmp, "Experiment Settings",  "Settings for this exp")
        self.toolbar.Bind(wx.EVT_TOOL, self.setExperimentSettings, id=self.IDs.tbExpSettings)
        self.toolbar.AddSimpleTool(self.IDs.tbCompile, compile_bmp, ("Compile Script [%s]" %self.app.keys['compileScript']).replace('Ctrl+', ctrlKey),  "Compile to script")
        self.toolbar.Bind(wx.EVT_TOOL, self.compileScript, id=self.IDs.tbCompile)
        self.toolbar.AddSimpleTool(self.IDs.tbRun, run_bmp, ("Run [%s]" %self.app.keys['runScript']).replace('Ctrl+', ctrlKey),  "Run experiment")
        self.toolbar.Bind(wx.EVT_TOOL, self.runFile, id=self.IDs.tbRun)
        self.toolbar.AddSimpleTool(self.IDs.tbStop, stop_bmp, ("Stop [%s]" %self.app.keys['stopScript']).replace('Ctrl+', ctrlKey),  "Stop experiment")
        self.toolbar.Bind(wx.EVT_TOOL, self.stopFile, id=self.IDs.tbStop)
        self.toolbar.EnableTool(self.IDs.tbStop,False)
        self.toolbar.Realize()

    def makeMenus(self):
        """ IDs are from app.wxIDs"""

        #---Menus---#000000#FFFFFF--------------------------------------------------
        menuBar = wx.MenuBar()
        #---_file---#000000#FFFFFF--------------------------------------------------
        self.fileMenu = wx.Menu()
        menuBar.Append(self.fileMenu, '&File')

        #create a file history submenu
        self.fileHistory = wx.FileHistory(maxFiles=10)
        self.recentFilesMenu = wx.Menu()
        self.fileHistory.UseMenu(self.recentFilesMenu)
        for filename in self.appData['fileHistory']: self.fileHistory.AddFileToHistory(filename)
        self.Bind(
            wx.EVT_MENU_RANGE, self.OnFileHistory, id=wx.ID_FILE1, id2=wx.ID_FILE9
            )

        self.fileMenu.Append(wx.ID_NEW,     "&New\t%s" %self.app.keys['new'])
        self.fileMenu.Append(wx.ID_OPEN,    "&Open...\t%s" %self.app.keys['open'])
        self.fileMenu.AppendSubMenu(self.recentFilesMenu,"Open &Recent")
        self.fileMenu.Append(wx.ID_SAVE,    "&Save\t%s" %self.app.keys['save'])
        self.fileMenu.Append(wx.ID_SAVEAS,  "Save &as...\t%s" %self.app.keys['saveAs'])
        self.fileMenu.Append(wx.ID_CLOSE,   "&Close file\t%s" %self.app.keys['close'])
        wx.EVT_MENU(self, wx.ID_NEW,  self.app.newBuilderFrame)
        wx.EVT_MENU(self, wx.ID_OPEN,  self.fileOpen)
        wx.EVT_MENU(self, wx.ID_SAVE,  self.fileSave)
        self.fileMenu.Enable(wx.ID_SAVE, False)
        wx.EVT_MENU(self, wx.ID_SAVEAS,  self.fileSaveAs)
        wx.EVT_MENU(self, wx.ID_CLOSE,  self.closeFrame)
        item = self.fileMenu.Append(wx.ID_PREFERENCES, text = "&Preferences")
        self.Bind(wx.EVT_MENU, self.app.showPrefs, item)
        #-------------quit
        self.fileMenu.AppendSeparator()
        self.fileMenu.Append(wx.ID_EXIT, "&Quit\t%s" %self.app.keys['quit'], "Terminate the program")
        wx.EVT_MENU(self, wx.ID_EXIT, self.quit)

        self.editMenu = wx.Menu()
        menuBar.Append(self.editMenu, '&Edit')
        self.editMenu.Append(wx.ID_UNDO, "Undo\t%s" %self.app.keys['undo'], "Undo last action", wx.ITEM_NORMAL)
        wx.EVT_MENU(self, wx.ID_UNDO,  self.undo)
        self.editMenu.Append(wx.ID_REDO, "Redo\t%s" %self.app.keys['redo'], "Redo last action", wx.ITEM_NORMAL)
        wx.EVT_MENU(self, wx.ID_REDO,  self.redo)

        #---_tools---#000000#FFFFFF--------------------------------------------------
        self.toolsMenu = wx.Menu()
        menuBar.Append(self.toolsMenu, '&Tools')
        self.toolsMenu.Append(self.IDs.monitorCenter, "Monitor Center", "To set information about your monitor")
        wx.EVT_MENU(self, self.IDs.monitorCenter,  self.app.openMonitorCenter)

        self.toolsMenu.Append(self.IDs.compileScript, "Compile\t%s" %self.app.keys['compileScript'], "Compile the exp to a script")
        wx.EVT_MENU(self, self.IDs.compileScript,  self.compileScript)
        self.toolsMenu.Append(self.IDs.runFile, "Run\t%s" %self.app.keys['runScript'], "Run the current script")
        wx.EVT_MENU(self, self.IDs.runFile,  self.runFile)
        self.toolsMenu.Append(self.IDs.stopFile, "Stop\t%s" %self.app.keys['stopScript'], "Abort the current script")
        wx.EVT_MENU(self, self.IDs.stopFile,  self.stopFile)

        self.toolsMenu.AppendSeparator()
        self.toolsMenu.Append(self.IDs.openUpdater, "PsychoPy updates...", "Update PsychoPy to the latest, or a specific, version")
        wx.EVT_MENU(self, self.IDs.openUpdater,  self.app.openUpdater)

        #---_view---#000000#FFFFFF--------------------------------------------------
        self.viewMenu = wx.Menu()
        menuBar.Append(self.viewMenu, '&View')
        self.viewMenu.Append(self.IDs.openCoderView, "&Open Coder view\t%s" %self.app.keys['switchToCoder'], "Open a new Coder view")
        wx.EVT_MENU(self, self.IDs.openCoderView,  self.app.showCoder)
        self.viewMenu.Append(self.IDs.tbIncrFlowSize, "&Flow Larger\t%s" %self.app.keys['largerFlow'], "Larger flow items")
        wx.EVT_MENU(self, self.IDs.tbIncrFlowSize, self.flowPanel.increaseSize)
        self.viewMenu.Append(self.IDs.tbDecrFlowSize, "&Flow Smaller\t%s" %self.app.keys['smallerFlow'], "Smaller flow items")
        wx.EVT_MENU(self, self.IDs.tbDecrFlowSize, self.flowPanel.decreaseSize)
        self.viewMenu.Append(self.IDs.tbIncrRoutineSize, "&Routine Larger\t%s" %self.app.keys['largerRoutine'], "Larger routine items")
        wx.EVT_MENU(self, self.IDs.tbIncrRoutineSize, self.routinePanel.increaseSize)
        self.viewMenu.Append(self.IDs.tbDecrRoutineSize, "&Routine Smaller\t%s" %self.app.keys['smallerRoutine'], "Smaller routine items")
        wx.EVT_MENU(self, self.IDs.tbDecrRoutineSize, self.routinePanel.decreaseSize)


        #---_experiment---#000000#FFFFFF--------------------------------------------------
        self.expMenu = wx.Menu()
        menuBar.Append(self.expMenu, '&Experiment')
        self.expMenu.Append(self.IDs.newRoutine, "&New Routine\t%s" %self.app.keys['newRoutine'], "Create a new routine (e.g. the trial definition)")
        wx.EVT_MENU(self, self.IDs.newRoutine,  self.addRoutine)
        self.expMenu.Append(self.IDs.copyRoutine, "&Copy Routine\t%s" %self.app.keys['copyRoutine'], "Copy the current routine so it can be used in another exp", wx.ITEM_NORMAL)
        wx.EVT_MENU(self, self.IDs.copyRoutine,  self.onCopyRoutine)
        self.expMenu.Append(self.IDs.pasteRoutine, "&Paste Routine\t%s" %self.app.keys['pasteRoutine'], "Paste the Routine into the current experiment", wx.ITEM_NORMAL)
        wx.EVT_MENU(self, self.IDs.pasteRoutine,  self.onPasteRoutine)
        self.expMenu.AppendSeparator()

        self.expMenu.Append(self.IDs.addRoutineToFlow, "Insert Routine in Flow", "Select one of your routines to be inserted into the experiment flow")
        wx.EVT_MENU(self, self.IDs.addRoutineToFlow,  self.flowPanel.onInsertRoutine)
        self.expMenu.Append(self.IDs.addLoopToFlow, "Insert Loop in Flow", "Create a new loop in your flow window")
        wx.EVT_MENU(self, self.IDs.addLoopToFlow,  self.flowPanel.insertLoop)

        #---_demos---#000000#FFFFFF--------------------------------------------------
        #for demos we need a dict where the event ID will correspond to a filename

        self.demosMenu = wx.Menu()
        #unpack demos option
        self.demosMenu.Append(self.IDs.builderDemosUnpack, "&Unpack Demos...",
            "Unpack demos to a writable location (so that they can be run)")
        wx.EVT_MENU(self, self.IDs.builderDemosUnpack, self.demosUnpack)
        self.demosMenu.AppendSeparator()
        self.demosMenuUpdate()#add any demos that are found in the prefs['demosUnpacked'] folder
        menuBar.Append(self.demosMenu, '&Demos')

        #---_help---#000000#FFFFFF--------------------------------------------------
        self.helpMenu = wx.Menu()
        menuBar.Append(self.helpMenu, '&Help')
        self.helpMenu.Append(self.IDs.psychopyHome, "&PsychoPy Homepage", "Go to the PsychoPy homepage")
        wx.EVT_MENU(self, self.IDs.psychopyHome, self.app.followLink)
        self.helpMenu.Append(self.IDs.builderHelp, "&PsychoPy Builder Help", "Go to the online documentation for PsychoPy Builder")
        wx.EVT_MENU(self, self.IDs.builderHelp, self.app.followLink)

        self.helpMenu.AppendSeparator()
        self.helpMenu.Append(wx.ID_ABOUT, "&About...", "About PsychoPy")
        wx.EVT_MENU(self, wx.ID_ABOUT, self.app.showAbout)

        self.SetMenuBar(menuBar)

    def closeFrame(self, event=None, checkSave=True):

        if self.app.coder==None and sys.platform!='darwin':
            if not self.app.quitting:
                self.app.quit()
                return#app.quit() will have closed the frame already

        if checkSave:
            ok=self.checkSave()
            if not ok: return False
        if self.filename==None:
            frameData=self.appData['defaultFrame']
        else:
            frameData = dict(self.appData['defaultFrame'])
            self.appData['prevFiles'].append(self.filename)
        #get size and window layout info
        if self.IsIconized():
            self.Iconize(False)#will return to normal mode to get size info
            frameData['state']='normal'
        elif self.IsMaximized():
            self.Maximize(False)#will briefly return to normal mode to get size info
            frameData['state']='maxim'
        else:
            frameData['state']='normal'
        frameData['auiPerspective'] = self._mgr.SavePerspective()
        frameData['winW'], frameData['winH']=self.GetSize()
        frameData['winX'], frameData['winY']=self.GetPosition()
        for ii in range(self.fileHistory.GetCount()):
            self.appData['fileHistory'].append(self.fileHistory.GetHistoryFile(ii))

        #assign the data to this filename
        self.appData['frames'][self.filename] = frameData
        self.app.allFrames.remove(self)
        self.app.builderFrames.remove(self)
        #close window
        self.Destroy()
        return 1#indicates that check was successful
    def quit(self, event=None):
        """quit the app"""
        self.app.quit()
    def fileNew(self, event=None, closeCurrent=True):
        """Create a default experiment (maybe an empty one instead)"""
        # check whether existing file is modified
        if closeCurrent: #if no exp exists then don't try to close it
            if not self.fileClose(): return False #close the existing (and prompt for save if necess)
        self.filename='untitled.psyexp'
        self.exp = experiment.Experiment(prefs=self.app.prefs)
        default_routine = 'trial'
        self.exp.addRoutine(default_routine) #create the trial routine as an example
        self.exp.flow.addRoutine(self.exp.routines[default_routine], pos=1)#add it to flow
        self.exp.namespace.add(default_routine, self.exp.namespace.user) # add it to user's namespace
        self.resetUndoStack()
        self.setIsModified(False)
        self.updateAllViews()
    def fileOpen(self, event=None, filename=None, closeCurrent=True):
        """Open a FileDialog, then load the file if possible.
        """
        if filename==None:
            dlg = wx.FileDialog(self, message="Open file ...", style=wx.OPEN,
                wildcard="PsychoPy experiments (*.psyexp)|*.psyexp|Any file (*.*)|*")
            if dlg.ShowModal() != wx.ID_OK:
                return 0
            filename = dlg.GetPath()
        #did user try to open a script in Builder?
        if filename.endswith('.py'):
            self.app.showCoder(fileList=[filename])
            return
        #NB this requires Python 2.5 to work because of with... statement
        with WindowFrozen(self):#try to pause rendering until all panels updated
            if closeCurrent:
                if not self.fileClose(updateViews=False):
                    return False #close the existing (and prompt for save if necess)
            self.exp = experiment.Experiment(prefs=self.app.prefs)
            try:
                self.exp.loadFromXML(filename)
            except Exception, err:
                print "Failed to load %s. Please send the following to the PsychoPy user list" %filename
                traceback.print_exc()
                logging.flush()
            self.resetUndoStack()
            self.setIsModified(False)
            self.filename = filename
            #routinePanel.addRoutinePage() is done in routinePanel.redrawRoutines(), as called by self.updateAllViews()
            #update the views
            self.updateAllViews()#if frozen effect will be visible on thaw
    def fileSave(self,event=None, filename=None):
        """Save file, revert to SaveAs if the file hasn't yet been saved
        """
        if filename==None:
            filename = self.filename
        if filename.startswith('untitled'):
            if not self.fileSaveAs(filename):
                return False #the user cancelled during saveAs
        else:
            self.exp.saveToXML(filename)
        self.setIsModified(False)
        return True
    def fileSaveAs(self,event=None, filename=None):
        """
        """
        if filename==None: filename = self.filename
        initPath, filename = os.path.split(filename)

        os.getcwd()
        if sys.platform=='darwin':
            wildcard="PsychoPy experiments (*.psyexp)|*.psyexp|Any file (*.*)|*"
        else:
            wildcard="PsychoPy experiments (*.psyexp)|*.psyexp|Any file (*.*)|*.*"
        returnVal=False
        dlg = wx.FileDialog(
            self, message="Save file as ...", defaultDir=initPath,
            defaultFile=filename, style=wx.SAVE, wildcard=wildcard)
        if dlg.ShowModal() == wx.ID_OK:
            newPath = dlg.GetPath()
            #update exp name
            # if the file already exists, query whether it should be overwritten (default = yes)
            dlg2 = dialogs.MessageDialog(self,
                        message="File '%s' already exists.\n    OK to overwrite?" % (newPath),
                        type='Warning')
            if not os.path.exists(newPath) or dlg2.ShowModal() == wx.ID_YES:
                shortName = os.path.splitext(os.path.split(newPath)[1])[0]
                self.exp.setExpName(shortName)
                #actually save
                self.fileSave(event=None, filename=newPath)
                self.filename = newPath
                returnVal = 1
                try: dlg2.destroy()
                except: pass
            else:
                print "'Save-as' canceled; existing file NOT overwritten.\n"
        try: #this seems correct on PC, but not on mac
            dlg.destroy()
        except:
            pass
        self.updateWindowTitle()
        return returnVal
    def OnFileHistory(self, evt=None):
        # get the file based on the menu ID
        fileNum = evt.GetId() - wx.ID_FILE1
        path = self.fileHistory.GetHistoryFile(fileNum)
        self.setCurrentDoc(path)#load the file
        # add it back to the history so it will be moved up the list
        self.fileHistory.AddFileToHistory(path)
    def checkSave(self):
        """Check whether we need to save before quitting
        """
        if hasattr(self, 'isModified') and self.isModified:
            dlg = dialogs.MessageDialog(self,'Experiment has changed. Save before quitting?', type='Warning')
            resp = dlg.ShowModal()
            dlg.Destroy()
            if resp  == wx.ID_CANCEL: return False #return, don't quit
            elif resp == wx.ID_YES:
                if not self.fileSave(): return False #user might cancel during save
            elif resp == wx.ID_NO: pass #don't save just quit
        return 1
    def fileClose(self, event=None, checkSave=True, updateViews=True):
        """user closes the Frame, not the file; fileOpen() calls fileClose()"""
        if checkSave:
            ok = self.checkSave()
            if not ok: return False#user cancelled
        #close self
        self.routinePanel.removePages()
        self.filename = 'untitled.psyexp'
        self.resetUndoStack()#will add the current exp as the start point for undo
        if updateViews:
            self.updateAllViews()
        return 1
    def updateAllViews(self):
        self.flowPanel.draw()
        self.routinePanel.redrawRoutines()
        self.updateWindowTitle()
    def updateWindowTitle(self, newTitle=None):
        if newTitle==None:
            shortName = os.path.split(self.filename)[-1]
            newTitle='%s - PsychoPy Builder' %(shortName)
        self.SetTitle(newTitle)
    def setIsModified(self, newVal=None):
        """Sets current modified status and updates save icon accordingly.

        This method is called by the methods fileSave, undo, redo, addToUndoStack
        and it is usually preferably to call those than to call this directly.

        Call with ``newVal=None``, to only update the save icon(s)
        """
        if newVal==None:
            newVal= self.getIsModified()
        else: self.isModified=newVal
#        elif newVal==False:
#            self.lastSavedCopy=copy.copy(self.exp)
#            print 'made new copy of exp'
#        #then update buttons/menus
#        if newVal:
        self.toolbar.EnableTool(self.IDs.tbFileSave, newVal)
        self.fileMenu.Enable(wx.ID_SAVE, newVal)
    def getIsModified(self):
        return self.isModified
    def resetUndoStack(self):
        """Reset the undo stack. e.g. do this *immediately after* creating a new exp.

        Will implicitly call addToUndoStack() using the current exp as the state
        """
        self.currentUndoLevel=1#1 is current, 2 is back one setp...
        self.currentUndoStack=[]
        self.addToUndoStack()
        self.enableUndo(False)
        self.enableRedo(False)
        self.setIsModified(newVal=False)#update save icon if needed
    def addToUndoStack(self, action="", state=None):
        """Add the given ``action`` to the currentUndoStack, associated with the @state@.
        ``state`` should be a copy of the exp from *immediately after* the action was taken.
        If no ``state`` is given the current state of the experiment is used.

        If we are at end of stack already then simply append the action.
        If not (user has done an undo) then remove orphan actions and then append.
        """
        if state==None:
            state=copy.deepcopy(self.exp)
        #remove actions from after the current level
#        print 'before stack=', self.currentUndoStack
        if self.currentUndoLevel>1:
            self.currentUndoStack = self.currentUndoStack[:-(self.currentUndoLevel-1)]
            self.currentUndoLevel=1
        #append this action
        self.currentUndoStack.append({'action':action,'state':state})
        self.enableUndo(True)
        self.setIsModified(newVal=True)#update save icon if needed
#        print 'after stack=', self.currentUndoStack
    def undo(self, event=None):
        """Step the exp back one level in the @currentUndoStack@ if possible,
        and update the windows

        Returns the final undo level (1=current, >1 for further in past)
        or -1 if redo failed (probably can't undo)
        """
        if (self.currentUndoLevel)>=len(self.currentUndoStack):
            return -1#can't undo
        self.currentUndoLevel+=1
        self.exp = copy.deepcopy(self.currentUndoStack[-self.currentUndoLevel]['state'])
        #set undo redo buttons
        self.enableRedo(True)#if we've undone, then redo must be possible
        if (self.currentUndoLevel)==len(self.currentUndoStack):
            self.enableUndo(False)
        self.updateAllViews()
        self.setIsModified(newVal=True)#update save icon if needed
        # return
        return self.currentUndoLevel
    def redo(self, event=None):
        """Step the exp up one level in the @currentUndoStack@ if possible,
        and update the windows

        Returns the final undo level (0=current, >0 for further in past)
        or -1 if redo failed (probably can't redo)
        """
        if self.currentUndoLevel<=1:
            return -1#can't redo, we're already at latest state
        self.currentUndoLevel-=1
        self.exp = copy.deepcopy(self.currentUndoStack[-self.currentUndoLevel]['state'])
        #set undo redo buttons
        self.enableUndo(True)#if we've redone then undo must be possible
        if self.currentUndoLevel==1:
            self.enableRedo(False)
        self.updateAllViews()
        self.setIsModified(newVal=True)#update save icon if needed
        # return
        return self.currentUndoLevel
    def enableRedo(self,enable=True):
        self.toolbar.EnableTool(self.IDs.tbRedo,enable)
        self.editMenu.Enable(wx.ID_REDO,enable)
    def enableUndo(self,enable=True):
        self.toolbar.EnableTool(self.IDs.tbUndo,enable)
        self.editMenu.Enable(wx.ID_UNDO,enable)
    def demosUnpack(self, event=None):
        """Get a folder location from the user and unpack demos into it
        """
        #choose a dir to unpack in
        dlg = wx.DirDialog(parent=self, message="Location to unpack demos")
        if dlg.ShowModal()==wx.ID_OK:
            unpackFolder = dlg.GetPath()
        else:
            return -1#user cancelled
        # ensure it's an empty dir:
        if os.listdir(unpackFolder) != []:
            unpackFolder = os.path.join(unpackFolder, 'PsychoPy2 Demos')
            if not os.path.isdir(unpackFolder):
                os.mkdir(unpackFolder)
        misc.mergeFolder(os.path.join(self.paths['demos'], 'builder'), unpackFolder)
        self.prefs['unpackedDemosDir']=unpackFolder
        self.app.prefs.saveUserPrefs()
        self.demosMenuUpdate()
    def demoLoad(self, event=None):
        fileDir = self.demos[event.GetId()]
        files = glob.glob(os.path.join(fileDir,'*.psyexp'))
        if len(files)==0:
            print "Found no psyexp files in %s" %fileDir
        else:
            self.fileOpen(event=None, filename=files[0], closeCurrent=True)
    def demosMenuUpdate(self):
        #list available demos
        if len(self.prefs['unpackedDemosDir'])==0:
            return
        demoList = glob.glob(os.path.join(self.prefs['unpackedDemosDir'],'*'))
        demoList.sort(key=lambda entry: entry.lower)
        ID_DEMOS = \
            map(lambda _makeID: wx.NewId(), range(len(demoList)))
        self.demos={}
        for n in range(len(demoList)):
            self.demos[ID_DEMOS[n]] = demoList[n]
        for thisID in ID_DEMOS:
            junk, shortname = os.path.split(self.demos[thisID])
            if shortname.startswith('_') or shortname.lower().startswith('readme.'):
                continue #ignore 'private' or README files
            self.demosMenu.Append(thisID, shortname)
            wx.EVT_MENU(self, thisID, self.demoLoad)
    def runFile(self, event=None):
        #get abs path of expereiment so it can be stored with data at end of exp
        expPath = self.filename
        if expPath==None or expPath.startswith('untitled'):
            ok = self.fileSave()
            if not ok: return#save file before compiling script
        expPath = os.path.abspath(expPath)
        #make new pathname for script file
        fullPath = self.filename.replace('.psyexp','_lastrun.py')
        script = self.exp.writeScript(expPath=expPath)

        #set the directory and add to path
        folder, scriptName = os.path.split(fullPath)
        if len(folder)>0: os.chdir(folder)#otherwise this is unsaved 'untitled.psyexp'
        f = codecs.open(fullPath, 'w', 'utf-8')
        f.write(script.getvalue())
        f.close()
        try:
            self.stdoutFrame.getText()
        except:
            self.stdoutFrame=stdOutRich.StdOutFrame(parent=self, app=self.app, size=(700,300))

        sys.stdout = self.stdoutFrame
        sys.stderr = self.stdoutFrame

        #provide a running... message
        print "\n"+(" Running: %s " %(fullPath)).center(80,"#")
        self.stdoutFrame.lenLastRun = len(self.stdoutFrame.getText())

        self.scriptProcess=wx.Process(self) #self is the parent (which will receive an event when the process ends)
        self.scriptProcess.Redirect()#builder will receive the stdout/stdin

        if sys.platform=='win32':
            command = '"%s" -u "%s"' %(sys.executable, fullPath)# the quotes allow file paths with spaces
            #self.scriptProcessID = wx.Execute(command, wx.EXEC_ASYNC, self.scriptProcess)
            self.scriptProcessID = wx.Execute(command, wx.EXEC_ASYNC| wx.EXEC_NOHIDE, self.scriptProcess)
        else:
            fullPath= fullPath.replace(' ','\ ')#for unix this signifis a space in a filename
            command = '%s -u %s' %(sys.executable, fullPath)# the quotes would break a unix system command
            self.scriptProcessID = wx.Execute(command, wx.EXEC_ASYNC| wx.EXEC_MAKE_GROUP_LEADER, self.scriptProcess)
        self.toolbar.EnableTool(self.IDs.tbRun,False)
        self.toolbar.EnableTool(self.IDs.tbStop,True)
    def stopFile(self, event=None):
        success = wx.Kill(self.scriptProcessID,wx.SIGTERM) #try to kill it gently first
        if success[0] != wx.KILL_OK:
            wx.Kill(self.scriptProcessID,wx.SIGKILL) #kill it aggressively
        self.onProcessEnded(event=None)
    def onProcessEnded(self, event=None):
        """The script/exp has finished running
        """
        self.toolbar.EnableTool(self.IDs.tbRun,True)
        self.toolbar.EnableTool(self.IDs.tbStop,False)
        #update the output window and show it
        text=""
        if self.scriptProcess.IsInputAvailable():
            stream = self.scriptProcess.GetInputStream()
            text += stream.read()
        if self.scriptProcess.IsErrorAvailable():
            stream = self.scriptProcess.GetErrorStream()
            text += stream.read()
        if len(text):self.stdoutFrame.write(text) #if some text hadn't yet been written (possible?)
        if len(self.stdoutFrame.getText())>self.stdoutFrame.lenLastRun:
            self.stdoutFrame.Show()
            self.stdoutFrame.Raise()

        #provide a finished... message
        msg = "\n"+" Finished ".center(80,"#")#80 chars padded with #

        #then return stdout to its org location
        sys.stdout=self.stdoutOrig
        sys.stderr=self.stderrOrig
    def onCopyRoutine(self, event=None):
        """copy the current routine from self.routinePanel to self.app.copiedRoutine
        """
        r = copy.deepcopy(self.routinePanel.getCurrentRoutine())
        if r is not None:
            self.app.copiedRoutine = r
    def onPasteRoutine(self, event=None):
        """Paste the current routine from self.app.copiedRoutine to a new page
        in self.routinePanel after promting for a new name
        """
        if self.app.copiedRoutine == None: return -1
        defaultName = self.exp.namespace.makeValid(self.app.copiedRoutine.name)
        message = 'New name for copy of "%s"?  [%s]' % (self.app.copiedRoutine.name, defaultName)
        dlg = wx.TextEntryDialog(self, message=message, caption='Paste Routine')
        if dlg.ShowModal() == wx.ID_OK:
            routineName=dlg.GetValue()
            newRoutine = copy.deepcopy(self.app.copiedRoutine)
            if not routineName:
                routineName = defaultName
            newRoutine.name = self.exp.namespace.makeValid(routineName)
            self.exp.namespace.add(newRoutine.name)
            self.exp.addRoutine(newRoutine.name, newRoutine)#add to the experiment
            for newComp in newRoutine: # routine == list of components
                newName = self.exp.namespace.makeValid(newComp.params['name'])
                self.exp.namespace.add(newName)
                newComp.params['name'].val = newName
            self.routinePanel.addRoutinePage(newRoutine.name, newRoutine)#could do redrawRoutines but would be slower?
            self.addToUndoStack("paste Routine %s" % newRoutine.name)
        dlg.Destroy()
    def onURL(self, evt):
        """decompose the URL of a file and line number"""
        # "C:\\Program Files\\wxPython2.8 Docs and Demos\\samples\\hangman\\hangman.py", line 21,
        filename = evt.GetString().split('"')[1]
        lineNumber = int(evt.GetString().split(',')[1][5:])
        self.app.coder.gotoLine(filename,lineNumber)
        self.app.showCoder()
    def compileScript(self, event=None):
        script = self.exp.writeScript(expPath=None)#leave the experiment path blank
        name = os.path.splitext(self.filename)[0]+".py"#remove .psyexp and add .py
        self.app.showCoder()#make sure coder is visible
        self.app.coder.fileNew(filepath=name)
        self.app.coder.currentDoc.SetText(script.getvalue())
    def setExperimentSettings(self,event=None):
        component=self.exp.settings
        #does this component have a help page?
        if hasattr(component, 'url'):helpUrl=component.url
        else:helpUrl=None
        dlg = DlgExperimentProperties(frame=self,
            title='%s Properties' %self.exp.name,
            params = component.params,helpUrl=helpUrl,
            order = component.order)
        if dlg.OK:
            self.addToUndoStack("edit experiment settings")
            self.setIsModified(True)
    def addRoutine(self, event=None):
        self.routinePanel.createNewRoutine()

def getAbbrev(longStr, n=30):
    """for a filename (or any string actually), give the first
    10 characters, an ellipsis and then n-10 of the final characters"""
    if len(longStr)>35:
        return longStr[0:10]+'...'+longStr[(-n+10):]
    else:
        return longStr
def appDataToFrames(prefs):
    """Takes the standard PsychoPy prefs and returns a list of appData dictionaries, for the Builder frames.
    (Needed because prefs stores a dict of lists, but we need a list of dicts)
    """
    dat = prefs.appData['builder']
def framesToAppData(prefs):
    pass
def canBeNumeric(inStr):
    """Determines whether the input can be converted to a float
    (using a try: float(instr))
    """
    try:
        float(inStr)
        return True
    except:
        return False
def _relpath(path, start='.'):
    """This code is based on os.path.repath in the Python 2.6 distribution,
    included here for compatibility with Python 2.5"""

    if not path:
        raise ValueError("no path specified")

    start_list = os.path.abspath(start).split(os.path.sep)
    path_list = os.path.abspath(path).split(os.path.sep)

    # Work out how much of the filepath is shared by start and path.
    i = len(os.path.commonprefix([start_list, path_list]))

    rel_list = ['..'] * (len(start_list)-i) + path_list[i:]
    if not rel_list:
        return curdir
    return os.path.join(*rel_list)
