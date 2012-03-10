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
        return "git" in self.meta and self.meta["git"] == "True"

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

        meta_nodes = root.find("Metadata").findall("Meta")
        self.meta = dict([self._parseMetaElement(node) for node in meta_nodes])

        file_nodes = root.find("Files").findall("File")
        self.files = list([self._parseFileNode(node,folder) for node in file_nodes])

    def _parseFileNode(self,node,folder):
        file_type = node.get("type")
        file_class = _file_nodes.get(file_type)
        if file_class is None:
            raise RuntimeError("The file type {} could not be found".format(file_type))
        return file_class(node,folder)
        
        
    def _parseMetaElement(self,node):
        """ Parses a single meta element """
        name = node.get("name")
        val = node.get("val")
        return (name,val)
        
                


class FileNode(object):
    """ base class for filenodes in a project"""
    def __init__(self,node,folder):
        self.folder = folder
        self.path = node.get("path")

    @property
    def abspath(self):
        return os.path.abspath(os.path.join(self.folder,self.path))

    def __repr__(self):
        return self.path

    def open(self,*args,**kwargs):
        """ Opens the file """
        return open(self.abspath,*args,**kwargs)
    
class PythonFile(FileNode):
    """ Python source files. These should be OK to open in coder view """
    def __init__(self,node,folder):
        super(PythonFile,self).__init__(node,folder)
        
class ExperimentFile(PythonFile):
    """ Runnable coder experiments """
    def __init__(self,node,folder):
        self.runnable = True
        super(ExperimentFile,self).__init__(node,folder)


_file_nodes = {"python": PythonFile,"experiment": ExperimentFile}
