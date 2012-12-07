
# This file specifies defaults for psychopy prefs for ALL PLATFORMS

# Notes on usage for developers (not needed or intended for use when making or running experiments):
# - baseNoArch.spec is copied & edited to be platform specific when you run generateSpec.py
# - the resulting files are parsed by configobj at psychopy run time, for the user's platform
# - To make changes to prefs for all platforms: 1) edit baseNoArch.spec, 2) run generateSpec.py, 3) commit
# - To make a platform specific pref change, 1) edit generateSpec.py as needed, 2) run generateSpec.py, 3) commit
# - If this file is NOT named baseNoArch.spec, it will be auto-generated.

# The syntax of this file is as expected by ConfigObj (not python):
# - Put a tooltip in a comment just prior to the line:
# - Each line should have a default= ___, and it should appear as the last item on the line

#   [section_name]
#      # comment lines not right above a pref are not used in tooltips
#      # the tooltip for prefName1 goes here, on the line right above its spec
#      prefName1 = type(value1, value2, ..., default='___')

# NOT_IMPLEMENTED defaultTimeUnits = option('sec', 'frames', default='sec')


# General settings
[general]
    # which system to use as a backend for drawing
    winType = option('pyglet', 'pygame', default='pyglet')
    # the default units for windows and visual stimuli
    units = option('deg', 'norm', 'cm', 'pix', default='norm')
    # full screen is best for accurate timing
    fullscr = boolean(default='False')
    # enable subjects to use the mouse and GUIs during experiments
    allowGUI = boolean(default='True')
    # 'version' is for internal usage, not for the user
    version = string(default='')
    # Add paths here to your custom Python modules
    paths=list(default=list())

# Application settings, applied to coder, builder, & prefs windows
[app]
    # display tips when starting PsychoPy
    showStartupTips = boolean(default='True')
    # size of icons in the Coder and Builder toolbars (top of window)
    largeIcons = boolean(default='True')
    # what windows to display when PsychoPy starts
    defaultView = option('last', 'builder', 'coder', 'both', default='last')
    # will reset site & key prefs to defaults immediately
    resetSitePrefs = boolean(default='False')
    # save any unsaved prefences before closing the window
    autoSavePrefs = boolean(default='False')
    # enable features for debugging PsychoPy itself, including unit-tests
    debugMode = boolean(default='False')

# Settings for the Coder window
[coder]
    # a list of font names; the first one found on the system will be used
    codeFont = string(default='Helvetica')
    # a list of font names; the first one found on the system will be used
    commentFont = string(default='Comic Sans MS')
    # a list of font names; the first one found on the system will be used
    outputFont = string(default='Monaco')
    # Font size (in pts) takes an integer between 6 and 24
    codeFontSize = integer(6,24, default=14)
    # Font size (in pts) takes an integer between 6 and 24
    outputFontSize = integer(6,24, default=14)
    showSourceAsst = boolean(default=False)
    showOutput = boolean(default=True)
    reloadPrevFiles = boolean(default=True)
    # for coder shell window, which shell to use
    preferredShell = option('ipython','pyshell',default='pyshell')

# Settings for the Builder window
[builder]
    # whether to automatically reload a previously open experiment
    reloadPrevExp = boolean(default=False)
    # if False will create scripts with an 'easier' but more cluttered namespace
    unclutteredNamespace = boolean(default=False)
    # folder names for custom components; expects a comma-separated list
    componentsFolders = list(default=list('/Users/Shared/PsychoPy2/components'))
    # a list of components to hide (eg, because you never use them)
    hiddenComponents = list(default=list('PatchComponent'))
    # where the Builder demos are located on this computer (after unpacking)
    unpackedDemosDir = string(default='')
    # name of the folder where subject data should be saved (relative to the script)
    savedDataFolder = string(default='data')
    topFlow = boolean(default=False)
    # Panels arrangement: topFlow = Flow on top, Components on left
    topFlow = boolean(default=False)
    alwaysShowReadme = boolean(default=True)
    maxFavorites = integer(default=10)

# Settings for connections
[connections]
    # the http proxy for usage stats and auto-updating; format is 000.000.000.000:0000
    proxy = string(default="")
    # override the above proxy settings with values found in the environment (if possible)
    autoProxy = boolean(default=True)
    # allow PsychoPy to send anonymous usage stats; please allow if possible, its helps PsychoPy's development
    allowUsageStats = boolean(default=True)
    # allow PsychoPy to check for new features and bug fixes
    checkForUpdates = boolean(default=True)

# KeyBindings; new key bindings only take effect on restart; Ctrl not available on Mac (use Cmd)
[keyBindings]
    # open an existing file
    open = string(default='Ctrl+O')
    # start a new experiment or script
    new = string(default='Ctrl+N')
    # save a Builder or Coder file
    save = string(default='Ctrl+S')
    # save a Builder or Coder file under a new name
    saveAs = string(default='Ctrl+Shift+S')
    # close the Builder or Coder window
    close = string(default='Ctrl+W')
    # end the application (PsychoPy)
    quit = string(default='Ctrl+Q')

    # Coder: cut
    cut = string(default='Ctrl+X')
    # Coder: copy
    copy = string(default='Ctrl+C')
    # Coder: paste
    paste = string(default='Ctrl+V')
    # Coder: duplicate
    duplicate = string(default='Ctrl+D')
    # Coder: indent code by one level (4 spaces)
    indent = string(default='Ctrl+]')
    # Coder: reduce indentation by one level (4 spaces)
    dedent = string(default='Ctrl+[')
    # Coder: indent to fit python syntax
    smartIndent = string(default='Shift+Tab')
    # Coder: find
    find = string(default='Ctrl+F')
    # Coder: find again
    findAgain = string(default='Ctrl+G')
    # Coder: undo
    undo = string(default='Ctrl+Z')
    # Coder: redo
    redo = string(default='Ctrl+Shift+Z')
    # Coder: add a # to the start of the line(s)
    comment = string(default="Ctrl+'")
    # Coder: remove # from start of line(s)
    uncomment = string(default="Ctrl+Shift+'")
    # Coder: fold this block of code
    fold = string(default='Ctrl+Home')

    # Coder: check for basic syntax errors
    analyseCode = string(default='F4')
    # convert a Builder .psyexp script into a python script and open it in the Coder
    compileScript = string(default='F5')
    # launch a script, Builder or Coder, or run unit-tests
    runScript = string(default='Ctrl+R')
    # attempt to interrupt and halt a running script
    stopScript = string(default='Ctrl+.')

    # Coder: show / hide white-space dots
    toggleWhitespace = string(default='Ctrl+Shift+W')
    # Coder: show / hide end of line characters
    toggleEOLs = string(default='Ctrl+Shift+L')
    toggleIndentGuides = string(default='Ctrl+Shift+I')

    # Builder: create a new routine
    newRoutine = string(default='Ctrl+Shift+N')
    # Builder: copy an existing routine
    copyRoutine = string(default='Ctrl+Shift+C')
    # Builder: paste the copied routine
    pasteRoutine = string(default='Ctrl+Shift+V')
    # Coder: show / hide the output panel
    toggleOutputPanel = string(default='Ctrl+Shift+O')
    # switch to Builder window from Coder
    switchToBuilder = string(default='Ctrl+L')
    # switch to Coder window from Builder
    switchToCoder = string(default='Ctrl+L')
    # increase display size in Flow
    largerFlow = string(default='Ctrl+=')
    # decrease display size in Flow
    smallerFlow = string(default='Ctrl+-')
    # increase display size of Routines
    largerRoutine = string(default='Ctrl+Shift+=') # on mac book pro this is good
    # decrease display size of Routines
    smallerRoutine = string(default='Ctrl+Shift+-')
    #show or hide the readme (info) for this experiment if possible
    toggleReadme = string(default='Ctrl+I')