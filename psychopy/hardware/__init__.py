import sys, glob, collections
from itertools import imap,chain

from psychopy import logging
__all__=['forp','cedrus','minolta','pr', 'crs', 'ioLabs']




def getSerialPorts():
    """Finds the names of all (virtual) serial ports present on the system

    :returns:

    Returns an iterable with all the serial ports.
    """
    if sys.platform == "darwin":
        ports = [
            '/dev/tty.USA*', #keyspan twin adapter is usually USA28X13P1.1
            '/dev/tty.Key*', #some are Keyspan.1 or Keyserial.1
            '/dev/tty.modem*',
            '/dev/cu.usbmodem*', #for PR650
        ]
    elif sys.platform.startswith("linux"):
        ports = [
            "/dev/ttyACM?", # USB CDC devices (virtual serial ports)
            "/dev/ttyUSB?", # USB to serial adapters using the usb-serial kernel module
            "/dev/ttyS?",   # genuine serial ports usually /dev/ttyS0 or /dev/ttyS1
            ]
    elif sys.platform == "cygwin": # I don't think anyone has actually tried this
        ports = [
            "/dev/ttyS?", # Cygwin maps the windows serial ports like this
        ]
    elif sys.platform == "win32":
        # While PsychoPy does support using numeric values to specify
        # which serial port to use, it is better in this case to
        # provide a cannoncial name.
        return imap("COM{0}".format,xrange(11)) #COM0-10
    else:
        logging.error("We don't support serial ports on {0} yet!"
                      .format(sys.platform))
        return []
    
    # This creates an iterator for each glob expression. The glob
    # expressions are then chained together. This is more efficient
    # because it means we don't perform the lookups before we actually
    # need to.
    return chain.from_iterable(imap(glob.iglob,ports))

def toPortName(obj):
    """Creates a proper path name from a numeric value or a string"""

    # a numeric string can _never_ be a valid port so we assume the user meant int
    # fyi "1234".isdigit() -> True 
    if isinstance(obj,basestring) and obj.isdigit():
        obj = int(obj)
    
    if type(obj) in [int,float]:
        if sys.platform == "win32":
            return "COM{0}".format(obj)
        else:
            # If we are on a unix like operating take a wild guess
            return "/dev/ttyS{0}".format(obj)
        
    if isinstance(obj,basestring):
        return obj # Looks like we already have a proper path
    
    
    return obj

def getAllPhotometers():
    """Gets all available photometers. 
    The returned photometers may vary depending on which drivers are installed.
    Standalone PsychoPy ships with libraries for all supported photometers.
    """
    import minolta,pr,crs
    photometers = [pr.PR650,pr.PR655,minolta.LS100]
    if hasattr(crs,"ColorCAL"):
        photometers.append(crs.ColorCAL)

    return photometers

def getPhotometerByName(name):
    """Gets a Photometer class by name. 
    You can use either short names like pr650 or a long name like
    Photoresearch PR650.
    
    :parameters:
        name : The name of the device
    
    :returns: 
    Returns the photometer matching the passed in device
    name or none if we were unable to find it.

    """
    for photom in getAllPhotometers():
        # longName is used from the GUI and driverFor is for coders
        if name.lower() in photom.driverFor or name == photom.longName:
            return photom


        

    

def findPhotometer(ports=None, device=None):
    """Try to find a connected photometer/photospectrometer! 
    PsychoPy will sweep a series of serial ports trying to open them. If a port 
    successfully opens then it will try to issue a command to the device. If it 
    responds with one of the expected values then it is assumed to be the 
    appropriate device. 
    
    :parameters:
        
        ports : a list of ports to search
            Each port can be a string (e.g. 'COM1', ''/dev/tty.Keyspan1.1') or a 
            number (for win32 comports only). If none are provided then PsychoPy 
            will sweep COM0-10 on win32 and search known likely port names on OS X
            and linux.
            
        device : string giving expected device (e.g. 'PR650', 'PR655', 'LS110').
            If this is not given then an attempt will be made to find a device of 
            any type, but this often fails
            
    :returns:
    
        * An object representing the first photometer found
        * None if the ports didn't yield a valid response
        * None if there were not even any valid ports (suggesting a driver not being installed)
        
    e.g.::
    
        photom = findPhotometer(device='PR655') #sweeps ports 0 to 10 searching for a PR655
        print photom.getLum()
        if hasattr(photom, 'getSpectrum'):#can retrieve spectrum (e.g. a PR650)
            print photom.getSpectrum()
        
    """
    if isinstance(device,basestring):
        photometers = [getPhotometerByName(device)]
    elif isinstance(device,collections.Iterable):
        # if we find a string assume it is a name, otherwise treat it like a photometer
        photometers = [getPhotometerByName(d) if isinstance(d,basestring) else d for d in device]
    else:
        photometers = getAllPhotometers()

    
    #determine candidate ports
    if ports == None: 
        ports = getSerialPorts()
    elif type(ports) in [int,float] or isinstance(ports,basestring):
        ports=[ports] #so that we can iterate
        
    #go through each port in turn
    photom=None
    logging.info('scanning serial ports...')
    logging.flush()
    for thisPort in ports:
        logging.info('...'+str(thisPort)); logging.flush()
        for Photometer in photometers:
            try:
                photom = Photometer(port=thisPort)
            except Exception as ex:
                logging.error("Couldn't initialize photometer {0}: {1}".format(Photometer.__name__,ex))
                continue # We threw an exception so we should just skip ahead
            if photom.OK: 
                logging.info(' ...found a %s\n' %(photom.type)); logging.flush()
                #we're now sure that this is the correct device and that it's configured
                #now increase the number of attempts made to communicate for temperamental devices!
                if hasattr(photom,'setMaxAttempts'):photom.setMaxAttempts(10)
                return photom#we found one so stop looking
            else:
                if photom.com and photom.com.isOpen(): 
                    logging.info('closing port')
                    photom.com.close()

        #If we got here we didn't find one
        logging.info('...nope!\n\t'); logging.flush()
            
    return None
