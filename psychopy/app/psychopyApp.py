#!/usr/bin/env python

# Part of the PsychoPy library
# Copyright (C) 2012 Jonathan Peirce
# Distributed under the terms of the GNU General Public License (GPL).

import sys, psychopy
import StringIO, copy
if sys.argv[-1] in ['-v', '--version']:
    print 'PsychoPy2, version %s (c)Jonathan Peirce, 2012, GNU GPL license' %psychopy.__version__
    sys.exit()
if sys.argv[-1] in ['-h', '--help']:
    print """Starts the PsychoPy2 application.

Usage:  python PsychoPy.py [options] [file]

Without options or files provided starts the psychopy using prefs to
decide on the view(s) to open.  If optional [file] is provided action
depends on the type of the [file]:

 Python script 'file.py' -- opens coder

 Experiment design 'file.psyexp' -- opens builder

Options:
    -c, --coder, coder       opens coder view only
    -b, --builder, builder   opens builder view only

    --version        prints version and exits
    -h, --help       prints this help and exit

"""
    sys.exit()

# Ensure 2.8 version of wx
if not hasattr(sys, 'frozen'):
    import wxversion
    wxversion.ensureMinimal('2.8')
import wx
#NB keep imports to a minimum here because splash screen has not yet shown
#e.g. coder and builder are imported during app.__init__ because they take a while
from psychopy import preferences, logging#needed by splash screen for the path to resources/psychopySplash.png
from psychopy.app import connections
import sys, os, threading, time, platform

"""
knowing if the user has admin priv is generally a good idea, but not actually needed.
something below is messing with the unit-tests, probably subprocess; os.popen worked ok
# get UID early; psychopy should never need anything except plain-vanilla user
uid = '-1' # -1=undefined, 0=assumed to be root, 500+ = non-root (1000+ for debian-based?)
try:
    if sys.platform not in ['win32']:
        #from psychopy.core import shellCall # messed with tests -- could not select a test (!?!)
        import subprocess, shlex
        #uid = shellCall('id -u')
        proc = subprocess(shlex('id -u'), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        uid, err = proc.communicate()
        del proc
    else:
        try:
            import ctypes # only if necessary
            uid = '1000'
            if ctypes.windll.shell32.IsUserAnAdmin():
                uid = '0'
        except:
            pass
except:
    pass
"""
uidRootFlag = '.'
#if int(uid) < 500: # 500+ is a normal user on darwin, rhel / fedora / centos; probably 1000+ for debian / ubuntu
#    uidRootFlag = '!'


class PsychoSplashScreen(wx.SplashScreen):
    """
    Create a splash screen widget.
    """
    def __init__(self):
        prefs=preferences.Preferences()
        splashFile = os.path.join(prefs.paths['resources'], 'psychopySplash.png')
        aBitmap = wx.Image(name = splashFile).ConvertToBitmap()
        splashStyle = wx.SPLASH_CENTRE_ON_SCREEN | wx.NO_BORDER
        # Call the constructor with the above arguments in exactly the
        # following order.
        wx.SplashScreen.__init__(self, aBitmap, splashStyle,
                                 0, None)
        #setup statusbar
        self.SetBackgroundColour('WHITE')
        self.status = wx.StaticText(self, -1, "  Loading libraries..."+uidRootFlag,
                                    wx.Point(0,250),#splash image is 640x240
                                    wx.Size(520, 20), wx.ALIGN_LEFT|wx.ALIGN_TOP)
        self.status.SetMinSize(wx.Size(520,20))
        self.Fit()
        self.Close()

class MenuFrame(wx.Frame):
    """A simple, empty frame with a menubar that should be the last frame to close on a mac
    """
    def __init__(self, parent=None, ID=-1, app=None, title="PsychoPy2"):
        wx.Frame.__init__(self, parent, ID, title, size=(1,1))
        self.app=app

        self.menuBar = wx.MenuBar()

        self.viewMenu = wx.Menu()
        self.menuBar.Append(self.viewMenu, '&View')
        self.viewMenu.Append(self.app.IDs.openBuilderView, "&Open Builder view\t%s" %self.app.keys['switchToBuilder'], "Open a new Builder view")
        wx.EVT_MENU(self, self.app.IDs.openBuilderView,  self.app.showBuilder)
        self.viewMenu.Append(self.app.IDs.openCoderView, "&Open Coder view\t%s" %self.app.keys['switchToCoder'], "Open a new Coder view")
        wx.EVT_MENU(self, self.app.IDs.openCoderView,  self.app.showCoder)
        item=self.viewMenu.Append(wx.ID_EXIT, "&Quit\t%s" %self.app.keys['quit'], "Terminate the program")
        self.Bind(wx.EVT_MENU, self.app.quit, item)

        self.SetMenuBar(self.menuBar)
        self.Show()

class PsychoPyApp(wx.App):
    def OnInit(self):
        self.version=psychopy.__version__
        self.SetAppName('PsychoPy2')
        #show splash screen
        splash = PsychoSplashScreen()
        if splash:
            splash.Show()
        #LONG IMPORTS - these need to be imported after splash screen starts (they're slow)
        #but then that they end up being local so keep track in self
        splash.status.SetLabel("  Loading PsychoPy2..."+uidRootFlag)
        from psychopy.monitors import MonitorCenter
        from psychopy.app import coder, builder, wxIDs, urls
        #set default paths and prefs
        self.prefs = preferences.Preferences() #from preferences.py
        if self.prefs.app['debugMode']:
            logging.console.setLevel(logging.DEBUG)
        self.keys = self.prefs.keys
        self.prefs.pageCurrent = 0  # track last-viewed page of prefs, to return there
        self.IDs=wxIDs
        self.urls=urls.urls
        self.quitting=False
        #setup links for URLs
        #on a mac, don't exit when the last frame is deleted, just show a menu
        if sys.platform=='darwin':
            self.menuFrame=MenuFrame(parent=None, app=self)
        #get preferred view(s) from prefs and previous view
        if self.prefs.app['defaultView']=='last':
            mainFrame = self.prefs.appData['lastFrame']
        else:
            # configobjValidate should take care of this situation (?), but doesn't:
            if self.prefs.app['defaultView'] in ['last', 'coder', 'builder', 'both']:
                mainFrame = self.prefs.app['defaultView']
            else:
                self.prefs.app['defaultView'] = 'both'
                mainFrame = 'both'
        #fetch prev files if that's the preference
        if self.prefs.coder['reloadPrevFiles']:
            scripts=self.prefs.appData['coder']['prevFiles']
        else: scripts=[]
        if self.prefs.builder['reloadPrevExp'] and ('prevFiles' in self.prefs.appData['builder'].keys()):
            exps=self.prefs.appData['builder']['prevFiles']
        else: exps=[]
        #then override the prev files by command options and passed files
        if len(sys.argv)>1:
            if sys.argv[1]==__name__:
                args = sys.argv[2:] # program was excecuted as "python.exe PsychoPyIDE.py %1'
            else:
                args = sys.argv[1:] # program was excecuted as "PsychoPyIDE.py %1'
            #choose which frame to start with
            if args[0] in ['builder', '--builder', '-b']:
                    mainFrame='builder'
                    args = args[1:]#can remove that argument
            elif args[0] in ['coder','--coder', '-c']:
                    mainFrame='coder'
                    args = args[1:]#can remove that argument
            #did we get .py or .psyexp files?
            elif args[0][-7:]=='.psyexp':
                    mainFrame='builder'
                    exps=[args[0]]
            elif args[0][-3:]=='.py':
                    mainFrame='coder'
                    scripts=[args[0]]
        else:
            args=[]

        self.dpi = int(wx.GetDisplaySize()[0]/float(wx.GetDisplaySizeMM()[0])*25.4)
        if not (50<self.dpi<120): self.dpi=80#dpi was unreasonable, make one up

        #create both frame for coder/builder as necess
        self.coder = None
        self.builderFrames = []
        self.copiedRoutine=None
        self.allFrames=[]#these are ordered and the order is updated with self.onNewTopWindow
        if mainFrame in ['both', 'coder']: self.showCoder(fileList=scripts)
        if mainFrame in ['both', 'builder']: self.showBuilder(fileList=exps)

        #send anonymous info to www.psychopy.org/usage.php
        #please don't disable this - it's important for PsychoPy's development
        self._latestAvailableVersion=None
        self.updater=None
        if self.prefs.connections['checkForUpdates'] or self.prefs.connections['allowUsageStats']:
            connectThread = threading.Thread(target=connections.makeConnections, args=(self,))
            connectThread.start()

        if self.prefs.app['showStartupTips']:
            tipIndex = self.prefs.appData['tipIndex']
            tp = wx.CreateFileTipProvider(os.path.join(self.prefs.paths['resources'],"tips.txt"), tipIndex)
            showTip = wx.ShowTip(None, tp)
            self.prefs.appData['tipIndex'] = tp.GetCurrentTip()
            self.prefs.saveAppData()
            self.prefs.app['showStartupTips'] = showTip
            self.prefs.saveUserPrefs()
        self.Bind
        wx.EVT_IDLE(self, self.onIdle)
        return True
    def onIdle(self, evt):
        #if we have internet and haven't yet checked for updates then do so
        if self._latestAvailableVersion not in [-1, None] and \
          self.prefs.connections['checkForUpdates'] and \
          self.updater==None:#we have a network connection but not yet tried an update
            self.updater=connections.Updater(app=self)
            #check for updates
            self.updater.suggestUpdate(confirmationDlg=False)
        evt.Skip()

    def getPrimaryDisplaySize(self):
        """Get the size of the primary display (whose coords start (0,0))
        """
        return list(wx.Display(0).GetGeometry())[2:]
    def showCoder(self, event=None, fileList=None):
        from psychopy.app import coder#have to reimport because it is ony local to __init__ so far
        if self.coder==None:
            self.coder=coder.CoderFrame(None, -1,
                      title="PsychoPy2 Coder (IDE) (v%s)" %self.version,
                      files = fileList, app=self)
        self.coder.Show(True)
        self.SetTopWindow(self.coder)
        self.coder.Raise()
        self.coder.setOutputWindow()#takes control of sys.stdout
        self.allFrames.append(self.coder)
    def newBuilderFrame(self, event=None, fileName=None):
        from psychopy.app import builder#have to reimport because it is ony local to __init__ so far
        thisFrame = builder.BuilderFrame(None, -1,
                                  title="PsychoPy2 Experiment Builder (v%s)" %self.version,
                                  fileName=fileName, app=self)
        thisFrame.Show(True)
        thisFrame.Raise()
        self.SetTopWindow(thisFrame)
        self.builderFrames.append(thisFrame)
        self.allFrames.append(thisFrame)
    def showBuilder(self, event=None, fileList=[]):
        from psychopy.app import builder#have to reimport because it is ony local to __init__ so far
        for fileName in fileList:
            if os.path.isfile(fileName):
                self.newBuilderFrame(fileName=fileName)
        #create an empty Builder view if needed
        if len(self.builderFrames)==0:
            self.newBuilderFrame()
        #loop through all frames, from the back bringing each forward
        for thisFrame in self.allFrames:
            if thisFrame.frameType!='builder':continue
            thisFrame.Show(True)
            thisFrame.Raise()
            self.SetTopWindow(thisFrame)
    #def showShell(self, event=None):
    #    from psychopy.app import ipythonShell#have to reimport because it is ony local to __init__ so far
    #    if self.shell==None:
    #        self.shell = ipythonShell.ShellFrame(None, -1,
    #            title="IPython in PsychoPy (v%s)" %self.version, app=self)
    #        self.shell.Show()
    #        self.shell.SendSizeEvent()
    #    self.shell.Raise()
    #    self.SetTopWindow(self.shell)
    #    self.shell.SetFocus()
    def openUpdater(self, event=None):
        from psychopy.app import connections
        dlg = connections.InstallUpdateDialog(parent=None, ID=-1, app=self)

    def colorPicker(self, event=None):
        """Opens system color-picker, sets clip-board and parent.new_rgb = string [r,g,b].

        Note: units are psychopy -1..+1 rgb units to three decimal places, preserving 24-bit color
        """
        class ColorPicker(wx.Panel):
            def __init__(self, parent):
                wx.Panel.__init__(self, parent, wx.ID_ANY)
                rgb = 'None'
                dlg = wx.ColourDialog(self)
                dlg.GetColourData().SetChooseFull(True)
                if dlg.ShowModal() == wx.ID_OK:
                    data = dlg.GetColourData()
                    rgb = data.GetColour().Get()
                    rgb = map(lambda x: "%.3f" % ((x-127.5)/127.5),list(rgb))
                    rgb = '['+','.join(rgb)+']'
                    if wx.TheClipboard.Open():
                        #http://wiki.wxpython.org/AnotherTutorial#wx.TheClipboard
                        wx.TheClipboard.Clear()
                        wx.TheClipboard.SetData(wx.TextDataObject(str(rgb)))
                        wx.TheClipboard.Close()
                dlg.Destroy()
                parent.new_rgb = rgb
        frame = wx.Frame(None, wx.ID_ANY, "Color picker", size=(0,0)) # not shown
        ColorPicker(frame)
        new_rgb = frame.new_rgb # string; also on system clipboard, try wx.TheClipboard
        frame.Destroy()
        return new_rgb
    def openMonitorCenter(self,event):
        from psychopy.monitors import MonitorCenter
        frame = MonitorCenter.MainFrame(None,'PsychoPy2 Monitor Center')
        frame.Show(True)
    def MacOpenFile(self,fileName):
        logging.debug('PsychoPyApp: Received Mac file dropped event')
        if fileName.endswith('.py'):
            if self.coder==None:
                self.showCoder()
            self.coder.setCurrentDoc(fileName)
        elif fileName.endswith('.psyexp'):
            self.newBuilderFrame(fileName=fileName)
    def quit(self, event=None):
        logging.debug('PsychoPyApp: Quitting...')
        self.quitting=True
        #see whether any files need saving
        for frame in self.allFrames:
            try:#will fail if the frame has been shut somehow elsewhere
                ok=frame.checkSave()
            except:
                ok=False
            if not ok:
                logging.debug('PsychoPyApp: User cancelled shutdown')
                return#user cancelled quit

        #save info about current frames for next run
        if self.coder and len(self.builderFrames)==0:
            self.prefs.appData['lastFrame']='coder'
        elif self.coder==None:
            self.prefs.appData['lastFrame']='builder'
        else:
            self.prefs.appData['lastFrame']='both'

        #update app data while closing each frame
        self.prefs.appData['builder']['prevFiles']=[]#start with an empty list to be appended by each frame
        self.prefs.appData['coder']['prevFiles']=[]
        for frame in copy.copy(self.allFrames):
            if frame==None: continue
            frame.closeFrame(checkSave=False)#should update (but not save) prefs.appData
            self.prefs.saveAppData()#must do this before destroying the frame?
        if sys.platform=='darwin':
            self.menuFrame.Destroy()

        sys.exit()#really force a quit

    def showPrefs(self, event):
        from psychopy.app.preferencesDlg import PreferencesDlg
        logging.debug('PsychoPyApp: Showing prefs dlg')
        prefsDlg = PreferencesDlg(app=self)
        prefsDlg.Show()

    def showAbout(self, event):
        logging.debug('PsychoPyApp: Showing about dlg')

        licFile = open(os.path.join(self.prefs.paths['psychopy'],'LICENSE.txt'))
        license = licFile.read()
        licFile.close()

        msg = """For stimulus generation and experimental control in python.

PsychoPy depends on your feedback. If something doesn't work then
let me/us know at psychopy-users@googlegroups.com"""
        info = wx.AboutDialogInfo()
        info.SetName('PsychoPy')
        info.SetVersion('v'+psychopy.__version__)
        info.SetDescription(msg)

        info.SetCopyright('(C) 2002-2012 Jonathan Peirce')
        info.SetWebSite('http://www.psychopy.org')
        info.SetLicence(license)
        info.AddDeveloper('Jonathan Peirce')
        info.AddDeveloper('Yaroslav Halchenko')
        info.AddDeveloper('Jeremy Gray')
        info.AddDocWriter('Jonathan Peirce')
        info.AddDocWriter('Rebecca Sharman')

        wx.AboutBox(info)

    def followLink(self, event=None, url=None):
        """Follow either an event id (which should be a key to a url defined in urls.py)
        or follow a complete url (a string beginning "http://")
        """
        if event!=None:
            wx.LaunchDefaultBrowser(self.urls[event.GetId()])
        elif url!=None:
            wx.LaunchDefaultBrowser(url)


if __name__=='__main__':
    app = PsychoPyApp(0)
    app.MainLoop()
