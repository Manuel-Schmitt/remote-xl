import os
import shutil
import shutil
import logging
import json

from remoteXL import main

class Config():    
    
    def __init__(self,path:str):
        self._logger = logging.getLogger(__name__)
        self._config_path = path   
        self._last_modified = 0
        self._config_data = {}
        self._load_config()
     
    def get(self,name:str):
        try:
            return self._config_data[name]
        except AttributeError:
            return None
            
    def __setattr__(self, name, value):
        if name[0] == '_':
            object.__setattr__(self, name, value) 
        else:
            self._config_data[name] = value
            
    def __getattr__(self,name):
        if name in self._config_data:
            return self._config_data[name]
        else:
            return None
   
        
    def _load_config(self):       

        try:    
            with open(self._config_path, "r") as jsonfile:
                loaded_data =json.load(jsonfile)
            self._config_data = loaded_data
            self._last_modified = os.path.getmtime(self._config_path)
        except FileNotFoundError:
            self._logger.warning('Config file {} not found! Generating empty config file'.format(self._config_path))
            self.save_config()
        except json.decoder.JSONDecodeError:
            self._logger.warning('Config file {} corrupted! Generating empty config file'.format(self._config_path))
            corrupted_config = "corrupted_" + str(os.path.basename(self._config_path))
            shutil.move(self._config_path,os.path.join(os.path.dirname(self._config_path),corrupted_config))
            self.save_config()
            
        if self.known_connections is None:
            self.known_connections = []
        
            
    def _save_config(self):        
        try:    
            if os.path.exists(self._config_path):
                current_last_modified = os.path.getmtime(self._config_path)
                
                if current_last_modified > self._last_modified:
                    self._logger.warning('Config file {} was modified since last reload! \n    Changes will be ignored! Stop background service before changing the config file!'.format(self._config_path))
                    #TODO: Implement: Ask user what to do
            dir = os.path.dirname(self._config_path)
            if not os.path.exists(dir):
                os.makedirs(dir)
            with open(self._config_path, "w") as jsonfile:
                json.dump(self._config_data, jsonfile,indent=4)
        except PermissionError as e:
            self._logger.warning('Could not write to config file {} ! {} Continuing...'.format(self._config_path, str(e)))
            
        #except FileNotFoundError as e:
         #   self.logger.warning('Config file {} not found during saving! {} Continuing...'.format(self._config_path, str(e)))
    