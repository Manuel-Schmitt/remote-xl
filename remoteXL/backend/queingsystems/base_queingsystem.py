from abc import ABC, abstractmethod
import time
from pathlib import PurePosixPath



class BaseQuingsystem(ABC):
    
    
    @classmethod
    def name(self):
        return self.__name__
    
    @classmethod
    def displayname(cls):
        try:
            if cls._displayname is None:
                return cls.__name__
            return cls._displayname
        except AttributeError:
            return cls.__name__

    @staticmethod
    @abstractmethod
    def needed_settings():
        raise NotImplementedError
        #all allowed settings are listed below
        settings = []
        settings.append({
            'Name' : 'queue',
            'Label':'Queue',
            'Type' : 'LineEdit',
            'Default': 'StartText'
        })
         
        settings.append({
            'Name' : 'cpu',
            'Label':'CPU',
            'Type' : 'SpinBox',
            'Min' : '1',
            'Max' : '99',
            'Default' : '1',
        })
        settings.append({
            'Name' : 'walltime',
            'Label':'Walltime',
            'Type' : 'WalltimeWidget',
            'MaxDays' : '14',
            #Value of WalltimeWidgets is saved as string: 'days-hours:minutes'
        })      
         
        settings.append({
            'Name' : 'selection',
            'Label':'Select',
            'Type' : 'ComboBox',
            'Values' : ['1','2','3'],
            'Default' : '2'
        })
        
        return settings
    
    @classmethod
    @abstractmethod
    def allows_resubmission(cls,job):
        #return True if the quingsystem/jobscript reserves the resources for some time and allow the resubmission of the same ins/hkl files (with or without modification)
        #The local refinement job creates an empty 'RESTART' file as signal for the running job.
        return False
    
    @classmethod
    def wait_time(cls,job):
        #only used if allow_resubmission() returns True
        #return the wait time in seconds
        return 0
    
    
    @classmethod
    def output_filename(cls):
        #Name of the shelxl output file
        #The create_job_script method has to use this value.
        return 'shelxl.out'
    
    @classmethod
    def job_script_path(cls,job):
        #local path to the generated job script
        return job.ins_hkl_path.with_suffix('.job')
    
    @classmethod
    @abstractmethod
    def submit_job(cls,job):
        raise NotImplementedError
    
    @classmethod
    @abstractmethod
    def create_job_script(cls,job):
        #Create the script which is run ( by the queingsystem of the remote host) to execute shelxl
        #After the shelxl execution a file named 'DONE' has to be created in the remote_workdir   
        raise NotImplementedError
    
    @classmethod
    @abstractmethod
    def get_compute_node(cls,job):
        #return name of compute node as string
        raise NotImplementedError
    
    @classmethod
    @abstractmethod
    def kill_job(cls,job):
        raise NotImplementedError
    
    @staticmethod
    @abstractmethod
    def job_status(job):
        #return 'queued', 'running' or 'stopped'
        raise NotImplementedError
        
    @classmethod
    def create_workdir(cls,job) -> PurePosixPath:  
        #create workdir on remote host
        base_workdir = PurePosixPath('./remoteXL_jobs/')  
        basename = job.ins_hkl_path.name
        timestring = time.strftime('%d-%m-%y_%H-%M-%S')
        workdir = base_workdir / (basename + '_' + timestring)
        
        #Check if dir already exists
        exists = job.remote_host.run("test -d '{}'".format(workdir),hide=True,warn=True).ok
        for i in range(0,2):
            if not exists:
                break
            #Not pretty, but should never be necessary.
            workdir = PurePosixPath(str(workdir) + '_new')
            exists = job.remote_host.run("test -d '{}'".format(workdir),hide=True,warn=True).ok

        if exists:
            raise ValueError('Could not create new workdir.')    
        
        job.remote_host.run("mkdir -p '{}' ".format(workdir),hide=True)
        return workdir
    
    @classmethod
    def check_settings(cls,settings:dict):       
        #return None if ok or error message as string
        if settings['user'] == '':
            return 'Error: Username was not given'
        if settings['host'] == '':
            return 'Error: Host was not given'
        if settings['shelxlpath'] == '':
            return 'Error: Path to ShelXL was not given'      
        for needed in cls.needed_settings():
            if not needed['Name'] in settings['queingsystem']:
                return 'Error: {} was not given'.format(needed['Lable'])
        return None    
    
    @classmethod                    
    def all_subclasses(cls):
        return set(cls.__subclasses__()).union([s for c in cls.__subclasses__() for s in c.all_subclasses()])
        
    @classmethod
    def get_subclass_by_name(cls,name):       
        for subclass in cls.all_subclasses():
            if subclass.name() == name:
                return subclass
    
    @staticmethod
    def get_all_settings():   
        all_settings = []
        for subclass in BaseQuingsystem.all_subclasses():
            all_settings.append( {'Name':subclass.name(),'Displayname': subclass.displayname(), 'Settings':subclass.needed_settings()} )
        return all_settings    