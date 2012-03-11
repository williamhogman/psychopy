# Part of the PsychoPy library
# Copyright (C) 2012 Jonathan Peirce
# Distributed under the terms of the GNU General Public License (GPL).

import wx, copy
from os import path
from psychopy.app.builder.experiment import Param

class BaseComponent:
    """A template for components, defining the methods to be overridden"""
    def __init__(self, exp, parentName, name=''):
        self.type='Base'
        self.exp=exp#so we can access the experiment if necess
        self.parentName=parentName#to access the routine too if needed
        self.params={}
        self.params['name']=Param(name, valType='code',
            hint="Name of this component",
            label="Name")
        self.order=['name']#make name come first (others don't matter)
    def writeInitCode(self,buff):
        pass
    def writeFrameCode(self,buff):
        """Write the code that will be called every frame
        """
        pass
    def writeRoutineStartCode(self,buff):
        """Write the code that will be called at the beginning of
        a routine (e.g. to update stimulus parameters)
        """
        self.writeParamUpdates(buff, 'set every repeat')
    def writeRoutineEndCode(self,buff):
        """Write the code that will be called at the end of
        a routine (e.g. to save data)
        """
        pass
    def writeExperimentEndCode(self,buff):
        """Write the code that will be called at the end of
        an experiment (e.g. save log files or reset hardware)
        """
        pass
    def writeTimeTestCode(self,buff):
        """Original code for testing whether to draw.
        Most objects should migrate to using writeStartTestCode and writeEndTestCode
        """
        if self.params['duration'].val=='':
            buff.writeIndented("if (%(startTime)s <= t):\n" %(self.params))
        else:
            buff.writeIndented("if (%(startTime)s <= t < (%(startTime)s+%(duration)s)):\n" %(self.params))
    def writeStartTestCode(self,buff):
        """Test whether we need to start
        """
        if self.params['startType'].val=='time (s)':
            buff.writeIndented("if t>=%(startVal)s and %(name)s.status==NOT_STARTED:\n" %(self.params))
        elif self.params['startType'].val=='frame N':
            buff.writeIndented("if frameN>=%(startVal)s and %(name)s.status==NOT_STARTED:\n" %(self.params))
        elif self.params['startType'].val=='condition':
            buff.writeIndented("if (%(startVal)s) and %(name)s.status==NOT_STARTED:\n" %(self.params))
        else:
            raise "Not a known startType (%(startType)s) for %(name)s" %(self.params)
        buff.setIndentLevel(+1,relative=True)
        buff.writeIndented("#keep track of start time/frame for later\n" %self.params)
        buff.writeIndented("%(name)s.tStart=t#underestimates by a little under one frame\n" %self.params)
        buff.writeIndented("%(name)s.frameNStart=frameN#exact frame index\n" %self.params)
    def writeStopTestCode(self,buff):
        """Test whether we need to stop
        """
        if self.params['stopType'].val=='time (s)':
            buff.writeIndented("elif %(name)s.status==STARTED and t>=%(stopVal)s:\n" %(self.params))
        #duration in time (s)
        elif self.params['stopType'].val=='duration (s)' and self.params['startType'].val=='time (s)':
            buff.writeIndented("elif %(name)s.status==STARTED and t>=(%(startVal)s+%(stopVal)s):\n" %(self.params))
        elif self.params['stopType'].val=='duration (s)':#start at frame and end with duratio (need to use approximate)
            buff.writeIndented("elif %(name)s.status==STARTED and t>=(%(name)s.tStart+%(stopVal)s):\n" %(self.params))
        #duration in frames
        elif self.params['stopType'].val=='duration (frames)':
            buff.writeIndented("elif %(name)s.status==STARTED and frameN>=(%(name)s.frameNStart+%(stopVal)s):\n" %(self.params))
        #stop frame number
        elif self.params['stopType'].val=='frame N':
            buff.writeIndented("elif %(name)s.status==STARTED and frameN>=%(stopVal)s:\n" %(self.params))
        #end according to a condition
        elif self.params['stopType'].val=='condition':
            buff.writeIndented("elif %(name)s.status==STARTED and (%(stopVal)s):\n" %(self.params))
        else:
            raise "Didn't write any stop line for startType=%(startType)s, stopType=%(stopType)s" %(self.params)
        buff.setIndentLevel(+1,relative=True)

    def writeParamUpdates(self, buff, updateType):
        """write updates to the buffer for each parameter that needs it
        updateType can be 'experiment', 'routine' or 'frame'
        """
        #add this once all stimulus setXXX() methods have an autoLog argument
#        if updateType=='frame':
#            logStr = ", autoLog=False"
#            logComment="#updating too often to be worth logging"
#        else:
#            logStr = logComment=""

        for thisParamName in self.params.keys():
            thisParam=self.params[thisParamName]
            if thisParam.updates==updateType:
                if thisParamName=='color':
                    paramCaps=self.params['colorSpace'].upper() #setRGB, not setColor
                else:paramCaps=thisParamName.capitalize()
                buff.writeIndented("%s.set%s(%s)\n" %(self.params['name'],paramCaps, thisParam) )
    def checkNeedToUpdate(self, updateType):
        """Determine whether this component has any parameters set to repeat at this level

        usage::
            True/False = checkNeedToUpdate(self, updateType)

        """
        for thisParamName in self.params.keys():
            if thisParamName=='advancedParams':
                continue
            thisParam=self.params[thisParamName]
            if thisParam.updates==updateType:
                return True
        return False
    def getPosInRoutine(self):
        """Find the index (position) in the parent Routine (0 for top)
        """
        routine = self.exp.routines[self.parentName]
        return routine.index(self)
    def getType(self):
        return self.__class__.__name__
    def getShortType(self):
        return self.getType().replace('Component','')