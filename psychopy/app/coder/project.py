# Part of the PsychoPy library
# Copyright (C) 2012 PsychoPy Contributors
# Distributed under the terms of the GNU General Public License (GPL).
from lxml import etree
import os
import os.path
import logging

class Project(object):
    """ Class representing a PsychoPy coder project """

    @property
    def gitEnabled(self):
        return "git-url" in self.meta

    def loadFromXML(self,filename):
        """ Loads an xml file and parses it as project """
        
        parser = etree.XMLParser(remove_blank_text=True)

        folder = os.path.split(filename)[0]
        
        with open(filename) as f:
            self._doc = etree.XML(f.read(),parser)

        root = self._doc

        # Version checking etc
        
        filename_base  = os.path.basename(filename)
        
        if root.tag != "PsychoPy2project":
            logging.error("{} is not a valid .psyproj file {}".format(
                filename_base,root.tag))
                
            # todo: subclassed exception
            raise RuntimeError("Invalid project file")

        self.psychopyVersion = root.get("version")
        # If we break backward compat. add checks here

        meta_nodes = root.find("Metadata")

        self.meta = dict([self._parseMetaElement(node) for node in meta_nodes])
        
    def _parseMetaElement(self,node):
        """ Parses a single meta element """
        name = node.get("name")
        val = node.get("val")
        return (name,val)
        
                
     
