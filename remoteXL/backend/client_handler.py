import threading
from pathlib import Path
import logging
import uuid
from  multiprocessing.connection import Connection

from paramiko.ssh_exception import AuthenticationException

from remoteXL.backend.refinement_job import RefinementJob
from remoteXL.backend.queingsystems.base_queingsystem import BaseQuingsystem

#TODO: Explicit import needed for pyinstaller...
from remoteXL.backend.queingsystems.slurm import Slurm
from remoteXL.backend.queingsystems.sge import Sun_Grid_Engine

class ClientHandler(threading.Thread):
    def __init__(self,backend, client:Connection):
        super().__init__()
        self.client = client
        self.backend = backend
        self.logger = logging.getLogger(__name__)
        self.ins_hkl_path = None
        self.shelxl_args = ''
        
    def run(self):
        
        try:
            while not self.backend.stop_event.is_set():
            
                #The client sends an initial signal containing a list. 
                #client_signal[1] == refinement for a ShelXL call or client_signal[1} == settings if no sys.args where used when calling remoteXL
                if self.client.poll(5):         
                    client_signal =self.client.recv()
                else:
                    continue
                
                
                if client_signal[0] == 'init_refinement':    
                    self.ins_hkl_path = Path(client_signal[1])
                    if len(client_signal) > 2: 
                        self.shelxl_args = client_signal[2]
                    #Check again if files exist:
                    if not self.ins_hkl_path.with_suffix('.ins').is_file() or not self.ins_hkl_path.with_suffix('.hkl').is_file():                       
                        err_msg = "Background service could not find one of the following files.\n{}.ins\n{}.hkl".format(self.ins_hkl_path,self.ins_hkl_path)
                        self.logger.warning(err_msg)
                        self.client.send(['error',err_msg])
                        break
                    
                    
                    with self.backend.lock:
                        #Check if Job for this file is already running                    
                        if self.ins_hkl_path in self.backend.running_jobs:
                            job = [j for j in self.backend.running_jobs if j == self.ins_hkl_path][0]
                            if job.lock.locked():
                                err_msg = 'Refinement of this files is already running from another remoteXL client!'
                                self.logger.warning(err_msg)
                                self.client.send(['error',err_msg])
                                break
                            if job.remote_job_status == 'waiting':
                                #job should be waiting for new refinement cycle     
                                try:   
                                    #This may throw ValueError if not connected to remote host
                                    if job.is_waiting():       
                                        #TODO: Check what happens if ValueError is triggered.               
                                        self.client.send(['run',job.setting])
                                        continue
                                except ValueError:
                                    pass
                                
                            elif job.remote_job_status == 'running':
                                #Check if ins/res file was changed since start of refinement;
                                ins_changed = (job.ins_hash != RefinementJob.get_ins_hash(self.ins_hkl_path.with_suffix('.ins')))    
                                    
                                self.client.send(['running',job.setting,job.start_time_string,ins_changed])
                                continue

                    
                        #Check if defaults are set for this file
                        setting_id = None
                        default_setting = None
                        if str(self.ins_hkl_path) in  self.backend.config.file_defaults:
                            setting_id = self.backend.config.file_defaults[str(self.ins_hkl_path)]
                        elif  self.backend.config.global_default is not None:
                            setting_id = self.backend.config.global_default
                        if setting_id is not None:    
                            for setting in self.backend.config.known_settings:
                                if setting_id == setting['id']:
                                    default_setting = setting
                                    break
                                
                    
                    if default_setting is not None: 
                        self.client.send(['run',default_setting])              
                    else:
                        #When no setting is saved for this file, send signal to open select_setting gui
                        self.client.send(['select_setting'])
                        
                elif client_signal[0] == 'run_refinement':
                    setting = client_signal[1]
                    setting.update({'shelxl_args':self.shelxl_args})
                    if self.ins_hkl_path is None:
                        self.logger.warning('Error: No ins/hkl file was given')
                        self.client.send(['error','Error: No ins/hkl file was given'])
                        continue
                    
                    
                    refinement_job = None
                    with self.backend.lock:
                        #Check again if Job for this file is already running                    
                        if self.ins_hkl_path in self.backend.running_jobs:
                            job = [j for j in self.backend.running_jobs if j == self.ins_hkl_path][0]
                            if job.lock.locked():
                                err_msg = 'Refinement of this files is already running from another remoteXL client!'
                                self.logger.warning(err_msg)
                                self.client.send(['error',err_msg])
                                break
                            else:
                                refinement_job = job
                  
                    if refinement_job == None:
                        #Create new job
                        refinement_job = RefinementJob(self.backend,self.ins_hkl_path,setting)  
                    
                    try:
                        refinement_job.run(self.client)
                    except AuthenticationException:
                        continue
                    except Exception as e:
                        errorstring = '{}: {}'.format(type(e).__name__,str(e))
                        self.client.send(['error',errorstring])
                        raise e
                    
                        
                elif client_signal[0] == 'known_settings': 
                    with self.backend.lock:
                        self.client.send(self.backend.config.known_settings)  
                        
                elif client_signal[0] == 'queingsystems':   
                    self.client.send(BaseQuingsystem.get_all_settings())                  
                          
                elif client_signal[0] == 'new_setting':                      
                    self.add_setting(client_signal[1])  
                
                elif client_signal[0] == 'edit_setting':                      
                    self.add_setting(client_signal[1]) 
                elif client_signal[0] == 'delete_setting':
                    conection_id = client_signal[1]['id']                      
                    with self.backend.lock:
                        for c in self.backend.config.known_settings:
                            if c['id'] == conection_id:
                                self.backend.config.known_settings.remove(c)
                                break
               
                elif client_signal[0] == 'change_order':   
                    old_position = client_signal[1][0]
                    new_position = client_signal[1][1]
                    with self.backend.lock:
                        con = self.backend.config.known_settings.pop(old_position)
                        self.backend.config.known_settings.insert(new_position, con)
                
                elif client_signal[0] == 'set_global_default':
                    default_setting = client_signal[1]
                    with self.backend.lock:
                        self.backend.config.global_default = default_setting['id']
                        
                elif client_signal[0] == 'set_file_default':
                    default_setting = client_signal[1]
                    if len(client_signal) > 2:
                        file_path = client_signal[2]
                    elif self.ins_hkl_path is not None:
                        file_path = str(self.ins_hkl_path)
                    else:
                        raise AttributeError('File path was not given')
                    
                    with self.backend.lock:
                        self.backend.config.file_defaults.update({file_path:default_setting['id']})
       
                        
                elif client_signal[0] == 'config':
                    
                     #TODO implement settings
                    
                    #Return saved setting values 
                    self.client.send(['config'])
                    
                    
                elif client_signal[0] == 'auth':
                    self.logger.warning('Received auth signal in client handler! Continue.')
                    continue
                else:    
                    error_msg = "Client send unknown signal:\n{}".format(client_signal)
                    self.logger.warning(error_msg)
                    self.client.send(['error',error_msg])
                    continue         
                
        except EOFError:
            self.logger.debug("Connection to client closed")
        except ConnectionResetError:
            self.logger.error("Connection to client interrupted!")
        except Exception:
            self.logger.error("Unknown exception handling client!")
            raise
        finally:
            if not self.client.closed:
                self.client.close()   
            self.backend.config._config_data_changed = True


    def add_setting(self,data:dict):
        try:
            if data['remote']:
                cls = BaseQuingsystem.get_subclass_by_name(data['queingsystem']['name'])
                error = cls.check_settings(data)
                if error is not None:
                    self.client.send(['error',error])
                    return 
            else:
                #Check if shelXL Path exists
                if not Path(data['path']).is_file():
                    self.client.send(['error','File {} not found!'.format(data['path'])])
                    return 
            with self.backend.lock:  
                if 'id' in data:
                    for index,c in enumerate(self.backend.config.known_settings):
                        if c['id'] == data['id']:
                            self.backend.config.known_settings.remove(c)
                            self.backend.config.known_settings.insert(index, data)
                else:
                    new_id = uuid.uuid4().int & (1<<16)-1
                    while new_id in self.backend.config.known_settings:
                        new_id = uuid.uuid4().int & (1<<16)-1
                    con = {'id':new_id}
                    con.update(data)      
                    self.backend.config.known_settings.append(con)
            self.client.send(['ok'])                  
                    
        except Exception as e:
            errorstring = '{}: {}'.format(type(e).__name__,str(e))
            self.client.send(['error',errorstring])
            raise e
        

