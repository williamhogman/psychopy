from psychopy import logging
from bits import BitsBox
try:
    from pycrsltd.colorcal import ColorCAL
except ImportError:
    logging.warning("Couldn't import pycrsltd. ColorCAL will not be available")
else:
    if not hasattr(ColorCAL,"longName"):
        logging.warning("You are using an outdated versions of pycrsltd, "
                        "consider updating to a newer version.")

        # Monkey-patch our metadata into their class.
        setattr(ColorCAL,"longName","CRS ColorCAL")
        setattr(ColorCAL,"driverFor",["colorcal"])
