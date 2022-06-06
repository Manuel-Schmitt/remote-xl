from pathlib import Path
import shutil
import logging
import json


class Config():
    
    def __init__(self,backend,path:str):
        self._logger = logging.getLogger(__name__)
        self._backend = backend
        self._config_path = path   
        self._config_data_changed = False
        self._last_modified = 0
        self._config_data = {}
        self.known_settings = []
        self.running_jobs = []
        self.global_default = None
        self.file_defaults = {}
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
            self._config_data_changed = True
            
    def __getattr__(self,name):
        if name in self._config_data:
            self._config_data_changed = True
            return self._config_data[name]
        raise AttributeError('{} is no key in config data!'.format(name) )
         
    def _load_config(self):       
        with self._backend.lock:
            try:    
                with open(self._config_path, "r") as jsonfile:
                    loaded_data =json.load(jsonfile)
                self._config_data.update(loaded_data)
                self._last_modified = self._config_path.stat().st_mtime
                self._config_data_changed = False
            except FileNotFoundError:
                self._logger.warning('Config file %s not found! Generating empty config file',str(self._config_path))
                self._save_config()
            except json.decoder.JSONDecodeError:
                self._logger.warning('Config file %s corrupted! Generating empty config file', str(self._config_path))
                corrupted_config_path =  self._config_path.parent / ('corrupted_' + self._config_path.name)
                shutil.move(self._config_path,corrupted_config_path)
                self._save_config()
        
        
            
    def _save_config(self):        
        try:   
            if not self._config_data_changed:
                return
            with self._backend.lock:
                if self._config_path.is_file():
                    current_last_modified = self._config_path.stat().st_mtime
                    
                    if current_last_modified > self._last_modified:
                        #TODO: Implement: Ask user what to do
                        self._logger.warning('Config file %s was modified since last reload! \n    Changes will be ignored! Stop background service before changing the config file!', str(self._config_path))     
                
                self.running_jobs = []
                for job in self._backend.running_jobs:
                    self.running_jobs.append(job.to_json)
                
                with open(self._config_path, "w") as jsonfile:
                    json.dump(self._config_data, jsonfile,indent=4)
                    
                self._last_modified = self._config_path.stat().st_mtime
                self._config_data_changed = False  
        except PermissionError as e:
            self._logger.warning('Could not write to config file %s ! %s Continuing...',str(self._config_path), str(e))
            

    