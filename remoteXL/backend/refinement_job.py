import time
import logging

from threading import Lock
from pathlib import Path,PurePosixPath
from datetime import datetime
import io 
import hashlib
import re

from remoteXL.util import RepeatTimer
from remoteXL.backend.queingsystems.base_queingsystem import BaseQuingsystem
from remoteXL.backend.remote_connection import RemoteConnection


class RefinementJob():
    def __init__(self,backend,ins_hkl_path,setting:dict):
        self.logger = logging.getLogger(__name__)
        self.lock = Lock()             
        self.backend = backend
        self.queingsystem = BaseQuingsystem.get_subclass_by_name(setting['queingsystem']['name'])
        
        ###These vars have to be saved and loaded with 'to_json' and 'from_json' 
        self.ins_hkl_path = ins_hkl_path
        self.ins_hash = self.get_ins_hash(self.ins_path)
        self.start_time = 0  
        self.setting = setting
        self.remote_workdir = None  #Job dir in the home directory of the user
        self.job_id = None
        self.remote_job_status = None
        self._remote_rundir_string = None  #String consisting of compute-node-name:rundir-path. If this string is None, assume that the job runs in remote_workdir    
        ###
        
        self.delete_timer = None
        self.remote_host = None
        self.client = None
        
    def run(self,client):
        self.client = client
        if self.client == None or self.client.closed:
            raise ValueError('At job start: Client is None or not connected!')
        
        if self.lock.locked():
            raise RuntimeError('The job is already running with another client')
        
        with self.lock:
            
            self.remote_host = self.get_or_connect_remote_host()
            
            #TODO: only one update_timer per remote_host, user and queingsystem
            update_timer = RepeatTimer(10, self.update_remote_job_status)
            finish_timer = RepeatTimer(2, self.check_finish_gracefully)
            self.ins_hkl_path.with_suffix('.fin').unlink(missing_ok=True)           
            
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
                        self.restart_job()
                    else:
                        self.client.send(['error','Could not restart job. Try again.'])
                else:
                    self.update_remote_job_status()
                                    

                
                update_timer.start()
                finish_timer.start()        
                sleep_time = 1 
                #wait for job and copy results back
                while not self.backend.stop_event.is_set():
                    output_exists = self.remote_host.run("test -f '{}'".format(str(self.remote_output_path)),hide=True,warn=True).ok
                    if output_exists:
                        self.client.send(['remoteXL','Refinement was started'])
                        
                        self._remote_rundir_string = self.remote_rundir_string
                            
                            
                        with self.remote_host.client.open_sftp() as sftp_client:  
                            with sftp_client.open(str(self.remote_output_path),mode="r") as output_file:
                                encoding = self.remote_host.config.run.encoding or 'UTF-8'
                            
                                while not self.backend.stop_event.is_set():
                                    output = output_file.read().decode(encoding)
                                    
                                    if self.remote_host.run('test -f "{}"'.format(str(self.remote_workdir/'DONE')),hide=True,warn=True).ok:                                      
                                        self.get_results(wait=False)
                                        output += output_file.read().decode(encoding)
                                        self.client.send(['shelxl',output])
                                        break   
                                    #shelxle activates the load res button, when 'for all data' was in the output
                                    #So, all files need to be transferred back before this is send to the client.                                                                    
                                    if 'for all data' in output or 'Total elapsed time:' in output:
                                        finish_timer.cancel()
                                        self.get_results()
                                        output += output_file.read().decode(encoding)
                                        self.client.send(['shelxl',output])
                                        break
                                    if output == '' or output is None:
                                        if  self.remote_job_status == 'stopped':
                                            #TODO: Add error message
                                            self.get_results(wait=False)
                                            break
                                        self.client.send(['shelxl',output])
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
                if finish_timer.is_alive():
                    finish_timer.cancel() 
                    
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
        self.remote_host.put(str(self.job_script_path),str(self.remote_workdir))
        self.remote_host.put(io.StringIO("{} {}".format(self.ins_hkl_name,' '.join(self.setting['shelxl_args']))),str(self.remote_workdir/'START'))
        
        #submit job script
        self.job_id = self.queingsystem.submit_job(self)
        self.start_time = time.time()
        
        self.client.send(['remoteXL','Job submitted as {}@{}'.format(self.setting['user'],self.setting['host'])])
        self.client.send(['remoteXL','Job id: {}'.format(self.job_id)])
        
        
    def restart_job(self): 
        #To restart the job, the ins and hkl file need to be copied to the compute-nodes local run dir
        #This path is written by the job script to the remote_workdir/RUNDIR file and saved in the job.remote_rundir_string var.
            
        #Copy files to remote_workdir and afterwards to rundir with rsync or scp
        #This is a workaround for slow nfs syncs as it can take to long for the compute-node to see the new input files.
        self.remote_host.put(str(self.ins_path),str(self.remote_workdir))
        self.remote_host.put(str(self.hkl_path),str(self.remote_workdir))
               
        #If remote_rundir_string is None, assume that job runs in remote_workdir and so rsync/scp is necessary
        if self.remote_rundir_string is None:
            self.client.send(['remoteXL','Job restarted in {}'.format(str(self.remote_workdir))])
            return 
        
        #use rsync if it exists else scp    
        if self.remote_host.run("command -v rsync >/dev/null 2>&1 ",hide=True,warn=True).ok:
            hkl_copy = self.remote_host.run("rsync {} {}".format(str(self.remote_workdir / self.hkl_name),self.remote_rundir_string),hide=True,warn=True)
            ins_copy = self.remote_host.run("rsync {} {}".format(str(self.remote_workdir / self.ins_name),self.remote_rundir_string),hide=True,warn=True)
        if  self.remote_host.run("command -v scp >/dev/null 2>&1 ",hide=True,warn=True).ok:
            if not hkl_copy.ok:
                hkl_copy = self.remote_host.run("scp {} {}".format(str(self.remote_workdir / self.hkl_name),self.remote_rundir_string))
            if not ins_copy.ok:
                ins_copy = self.remote_host.run("scp {} {}".format(str(self.remote_workdir / self.ins_name),self.remote_rundir_string))
        
        if not hkl_copy.ok or not ins_copy.ok:
            raise RuntimeError('Could not  copy new ins and hkl file to "{}"!'.format(hkl_copy.ok))
        
        self.remote_job_status = 'running'
        self.client.send(['remoteXL','Job restarted in {}'.format(str(self.remote_rundir_string))])
        #Wait for refinement to restart.
        #If this does not happen in 60s, assume restart did not work
        timeout = 60
        start_time = time.time()
        while not self.backend.stop_event.is_set():
            output_exists = self.remote_host.run("test -f '{}'".format(str(self.remote_output_path)),hide=True,warn=True).ok
            if output_exists:
                break
            if time.time() > (start_time + timeout):
                raise RuntimeError('Refinement was not restarted!')
            time.sleep(1)
        
        
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
                    if self.remote_host.run('test -f "{}"'.format(str(self.remote_workdir/'DONE')),hide=True,warn=True).ok:
                        break
                    #TODO: 
                    #fcf_file_size = self.remote_host.sftp().stat(str(self.remote_workdir / (self.ins_hkl_name + '.fcf'))).st_size
                    #if fcf_file_size > 0:
                        #break
                except FileNotFoundError:
                    pass
                
                if timeout is not None:
                    if time.time() > (start_time + timeout):
                        raise FileNotFoundError('The results of the refinement were not present after timeout.')
                time.sleep(sleep_time)
        
        for file in self.remote_host.sftp().listdir(str(self.remote_workdir)):
            if file == self.hkl_name:
                continue
            if file == 'DONE':
                continue
            if file == 'RUNDIR' and self._remote_rundir_string is None:
                self._remote_rundir_string = self.remote_rundir_string
            self.remote_host.get(remote=str(self.remote_workdir / file),local=str(self.dir_path / file))
        
    
    def update_remote_job_status(self):    
        if self.remote_host is None or not self.remote_host.is_connected:
            self.remote_host = self.get_remote_host()
        status = self.queingsystem.job_status(self)
        if self.queingsystem.allows_resubmission(self) and status == 'running' and self.remote_job_status == 'waiting':
            #job script on remote host is in waiting loop
            self.remote_job_status = 'waiting'
        else: 
            self.remote_job_status = status
        
    def check_finish_gracefully(self):
        #If ins_hkl_path.fin file exists, finish gracefully was pressed in shelxle and this file needs to be copied to the remote host.
        fin_file_path = self.ins_hkl_path.with_suffix('.fin')
        if fin_file_path.is_file():
            self.ins_hkl_path.with_suffix('.fin').unlink(missing_ok=True)
            if self.remote_rundir_string is not None:
                self.remote_host.run('ssh {} "touch {}"'.format(self.compute_node,str(self.remote_rundir_path / fin_file_path.name )))
            else:
                self.remote_host.run('touch {}'.format(str(self.remote_workdir / fin_file_path.name )))

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
    def remote_rundir_path(self):
        return PurePosixPath(self.remote_rundir_string.split(':')[1])
    
    @property
    def remote_rundir_string(self):
        if self._remote_rundir_string is not None:
            return self._remote_rundir_string
        if self.remote_host.run("test -f '{}'".format(str(self.remote_workdir / 'RUNDIR')),hide=True,warn=True).ok:   
            self._remote_rundir_string = self.remote_host.run("cat '{}'".format(str(self.remote_workdir / 'RUNDIR')),hide=True).stdout.strip()
        return self._remote_rundir_string
    
    @property
    def compute_node(self):
        if self.remote_rundir_string is not None:
            return self.remote_rundir_string.split(':')[0]
        return self.queingsystem.get_compute_node(self)
    
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
    
    def kill_job(self):
        self.remote_host = self.get_remote_host()
        self.queingsystem.kill_job(self)
        self.remote_job_status = 'stopped'
        if self.lock.locked():
            #One client is in self.run and does the cleanup
            return
        
        with self.backend.lock:
            if self in self.backend.running_jobs:
                self.backend.running_jobs.remove(self)
    
        self.delete_remote_files(True)                      
    
    
    
    @property
    def to_json(self):
        data = {
            'local_file':str(self.ins_hkl_path),
            'remote_workdir':str(self.remote_workdir),
            'setting':self.setting,
            'job_id':self.job_id,
            'start_time':self.start_time,
            'status': self.remote_job_status,
            'rundir': self.remote_rundir_string,
            'ins_hash': self.ins_hash,
            
            }
        return data
    
    @classmethod
    def from_json(cls,backend,data):
        job = cls(backend,Path(data['local_file']),data['setting'])
        job.job_id = data['job_id']
        job.remote_workdir = PurePosixPath(data['remote_workdir'])
        job.start_time = data['start_time']
        job.remote_job_status = data['status']
        job._remote_rundir_string = data['rundir']
        job.ins_hash = data['ins_hash']
        return job

    @staticmethod
    def get_ins_hash(ins_path):
        with open(ins_path) as f:
            ins_content = f.read()
        #remove ANIS instructions, comments and whitespace from ins_content
        stripped_ins_content = re.sub(r'REM.*|!.*|ANIS|\s','',ins_content)
        return hashlib.md5(stripped_ins_content.encode('utf-8')).hexdigest()



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
                    self.client.send(['auth_ok']) 
                    return remote_connection
                         
        remote_connection = RemoteConnection.connect(self)             
            
        return remote_connection
        
    def __eq__(self,other):
        if isinstance(other, RefinementJob):
            return self.ins_hkl_path == other.ins_hkl_path
        if isinstance(other, Path):
            return self.ins_hkl_path == other
        if isinstance(other, str):
            return str(self.ins_hkl_path) == other
        return False 
        
