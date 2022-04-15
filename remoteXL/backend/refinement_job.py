import time
import logging
import traceback
from threading import Timer,Lock,Event
from pathlib import Path,PurePosixPath
from datetime import datetime


from remoteXL.backend.queingsystems.base_queingsystem import BaseQuingsystem
from remoteXL.backend.remote_connection import RemoteConnection

class RefinementJob():
    def __init__(self,backend,ins_hkl_path,setting:dict):
        self.logger = logging.getLogger(__name__)
        self.lock = Lock()             
        self.backend = backend
        self.queingsystem = BaseQuingsystem.get_subclass_by_name(setting['queingsystem']['name'])
        
        ###These vars have to be saved and loaded with 'to_json' and 'from_json' 
        self.ins_hkl_path = Path(ins_hkl_path)
        self.setting = setting
        self.remote_workdir = None
        self.job_id = None
        self.start_time = 0
        self.remote_job_status = None
        ###
        
        self.delete_timer = None
        
        
        
    def run(self,client):
        self.client = client
        if self.client == None or self.client.closed:
            raise ValueError('At job start: Client is None or not connected!')
        
        self.remote_host = self.get_or_connect_remote_host()
        
        if self.lock.locked():
            raise RuntimeError('The job is already running with another client')
        
        with self.lock:
            update_timer = RepeatTimer(10, self.update_remote_job_status)
            
            if self.delete_timer is not None and self.delete_timer.is_alive():
                self.delete_timer.cancel()
                self.delete_timer = None       
                
            try:
                #If self.remote_workdir and self.job_id are set, the job was already started. 
                if self.remote_workdir == None or self.job_id == None:
                    self.start_remote_job()
                    #add job to running job list
                    with self.backend.lock:
                        if not self in self.backend.running_jobs:
                            self.backend.running_jobs.append(self)     
                                  
                if self.remote_job_status == 'waiting':
                    #check if job is still waiting 
                    if self.is_waiting():                                                   
                        #copy files to remote host
                        self.remote_host.put(str(self.ins_path),str(self.remote_workdir))
                        self.remote_host.put(str(self.hkl_path),str(self.remote_workdir))
                        self.remote_host.run('cd {}; touch RESTART'.format(str(self.remote_workdir)))
                        self.remote_job_status = 'running'                  
                    else:
                        self.client.send(['error','Could not restart job. Try again.'])
                self.update_remote_job_status()
                                    

                
                update_timer.start()        
                sleep_time = 1 
                #wait for job and copy results back
                while not self.backend.stop_event.is_set():
                    output_exists = self.remote_host.run("test -f '{}'".format(str(self.remote_output_path)),hide=True,warn=True).ok
                    if output_exists:
                        self.client.send(['remoteXL','Refinement was started'])
                        with self.remote_host.sftp().open(str(self.remote_output_path),mode="r") as output_file:
                            encoding = self.remote_host.config.run.encoding or 'UTF-8'
        
                            while not self.backend.stop_event.is_set():
                                output = output_file.read().decode(encoding)
                                #shelxle activates the load res button, when 'for all data' was in the output
                                #So, all files need to be transferred back before this is send to the client.    
                                #shelxl ended with an error if the output contains '** <Error> **'                       
                                if 'for all data' in output or '**' in output:
                                    self.get_results()
                                    output += output_file.read().decode(encoding)
                                    self.client.send(['shelxl',output])
                                    break
                                if output == '':
                                    if  self.remote_job_status == 'stopped':
                                        self.get_results(wait=False)
                                        break
                                    time.sleep(sleep_time)
                                else:
                                    self.client.send(['shelxl',output])      
                            break
                        
                    else:
                        if self.remote_job_status == 'stopped':
                            with self.backend.lock:
                                if self in self.backend.running_jobs:
                                    self.backend.running_jobs.remove(self)
                            raise RuntimeError('Refinement job stopped, but no output was found!')
                        else:
                            time.sleep(sleep_time)
                    
                self.client.send(['shelxl_done'])
                        
                if self.backend.stop_event.is_set():
                    return
            
                
                
                #clean up  
                if self.queingsystem.allows_resubmission(self) and self.remote_job_status == 'running':
                    self.delete_remote_files(False)
                    self.remote_job_status = 'waiting'
                    self.delete_timer = RepeatTimer(60, self.delayed_delete,start_delay=self.queingsystem.wait_time(self))
                    self.delete_timer.start()
                    
                else:
                    with self.backend.lock:
                        if self in self.backend.running_jobs:
                            self.backend.running_jobs.remove(self)
                            
                    self.delete_remote_files(True)
                
            finally:       
                self.client = None
                if update_timer.is_alive():
                    update_timer.cancel() 
    def start_remote_job(self):
        #create job script locally
        self.queingsystem.create_job_script(self)
        
        #create workdir on remote host
        self.remote_workdir = self.queingsystem.create_workdir(self)
        #check that this job is not running directly in the home dir     
        if self.remote_workdir == PurePosixPath() or self.remote_workdir == None :                      
            raise ValueError('remote_workdir was set to an empty path!')
        
        #copy files to remote host
        self.remote_host.put(str(self.ins_path),str(self.remote_workdir))
        self.remote_host.put(str(self.hkl_path),str(self.remote_workdir))
        self.remote_host.put(str(self.job_script_path),str(self.remote_workdir))
        
        #submit job script
        self.job_id = self.queingsystem.submit_job(self)
        self.start_time = time.time()
        
        self.client.send(['remoteXL','Job submitted as {}@{}'.format(self.setting['user'],self.setting['host'])])
        self.client.send(['remoteXL','Job id: {}'.format(self.job_id)])
        

    def is_waiting(self):
        if self.remote_host is None or not self.remote_host.is_connected:
            self.remote_host = self.get_remote_host()
        self.update_remote_job_status()
        if self.remote_job_status == 'waiting':
            return True
        elif self.remote_job_status == 'stopped':
            self.delayed_delete()
            return False
            
    def delayed_delete(self):
            if self.remote_host is None or not self.remote_host.is_connected:
                self.remote_host = self.get_remote_host()
            self.update_remote_job_status()
            if self.remote_job_status == 'stopped':
                with self.backend.lock:
                    if self in self.backend.running_jobs:
                        self.backend.running_jobs.remove(self)
                self.delete_remote_files(True)
                if self.delete_timer is not None and self.delete_timer.is_alive():
                    self.delete_timer.cancel()
                    self.delete_timer = None   
            
    def delete_remote_files(self,include_workdir=False):
        if self.remote_workdir == PurePosixPath() or self.remote_workdir == None :                      
            raise ValueError('remote_workdir was set to an empty path!')
        if include_workdir:
            self.remote_host.run("rm -rf {}".format(self.remote_workdir),hide=True,warn=True)
        else:
            self.remote_host.run("rm  -rf {}/*".format(self.remote_workdir),hide=True,warn=True)
            
    def get_results(self,wait=True,timeout=60):     
        #wait until results are present in remote_workdir
        #generous timeout of 60s should be enough   
        if wait:
            sleep_time = 1 
            start_time = time.time()
            while not self.backend.stop_event.is_set():
                try:
                    fcf_file_size = self.remote_host.sftp().stat(str(self.remote_workdir / (self.ins_hkl_name + '.fcf'))).st_size
                    if fcf_file_size > 0:
                        break
                except FileNotFoundError:
                    pass
                
                if timeout is not None:
                    if time.time() > (start_time + timeout):
                        raise FileNotFoundError('The results of the refinement were not present after timeout.')
                time.sleep(sleep_time)
        
        for file in self.remote_host.sftp().listdir(str(self.remote_workdir)):
            self.remote_host.get(remote=str(self.remote_workdir / file),local=str(self.dir_path / file))
        
    
    def update_remote_job_status(self):    
        status = self.queingsystem.job_status(self)
        if self.queingsystem.allows_resubmission(self) and status == 'running' and self.remote_job_status == 'waiting':
            #job script on remote host is in waiting loop
            self.remote_job_status = 'waiting'
        else: 
            self.remote_job_status = status
        
    @property
    def remote_output_path(self):
        return self.remote_workdir / self.queingsystem.output_filename()
    
    @property
    def job_script_path(self):
        return self.queingsystem.job_script_path(self)
    
    @property
    def dir_path(self):
        return self.ins_hkl_path.parent
    
    @property
    def ins_hkl_name(self):     
        return self.ins_hkl_path.name
    @property
    def ins_name(self):     
        return self.ins_hkl_path.name + '.ins'
    @property
    def hkl_name(self):     
        return self.ins_hkl_path.name + '.hkl'
        
    @property
    def ins_path(self):
        return self.ins_hkl_path.with_suffix('.ins')
         
    
    @property
    def hkl_path(self):
        return self.ins_hkl_path.with_suffix('.hkl')   
    
    @property
    def start_time_string(self):
        return datetime.fromtimestamp(self.start_time).strftime("%H:%M:%S (%d-%B-%Y)")
        
    @property
    def to_json(self):
        data = {
            'local_file':str(self.ins_hkl_path),
            'remote_workdir':str(self.remote_workdir),
            'setting':self.setting,
            'job_id':self.job_id,
            'start_time':self.start_time,
            'status': self.remote_job_status
            
            }
        return data
    
    @classmethod
    def from_json(cls,backend,data):
        job = cls(backend,data['local_file'],data['setting'])
        job.job_id = data['job_id']
        job.remote_workdir = PurePosixPath(data['remote_workdir'])
        job.start_time = data['start_time']
        job.remote_job_status = data['status']
        return job
        
    def get_remote_host(self):
        with self.backend.lock:
            for rc in self.backend.remote_connections:
                if not rc.is_connected:
                    self.backend.remote_connections.remove(rc)
                    continue
                if rc.host == self.setting['host'] and rc.user == self.setting['user']:
                    return rc
        raise ValueError('No connection to {}@{} found'.format(self.setting['user'],self.setting['host']))
    
    def get_or_connect_remote_host(self):
        remote_connection = None
        
        with self.backend.lock:
            #Check if Connection exists 
            for rc in self.backend.remote_connections:
                if not rc.is_connected:
                    self.backend.remote_connections.remove(rc)
                    continue
                if rc.host == self.setting['host'] and rc.user == self.setting['user']:
                    remote_connection = rc
                    
        if remote_connection == None:   
            remote_connection = RemoteConnection.connect(self)             
            with self.backend.lock:
                self.backend.remote_connections.append(remote_connection)  
        
        self.client.send(['auth_ok'])  
        
        return remote_connection
        
    def __eq__(self,other):
        if isinstance(other, RefinementJob):
            return self.ins_hkl_path == other.ins_hkl_path
        if isinstance(other, Path):
            return self.ins_hkl_path == other
        if isinstance(other, str):
            return str(self.ins_hkl_path) == other
        return False 
        
       
       
        
class RepeatTimer(Timer):
    def __init__(self,interval, function,start_delay=0):
        super().__init__(interval, function)
        self.start_delay = start_delay
        self.daemon = True
        
    def run(self):
        self.finished.wait(self.start_delay)
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)