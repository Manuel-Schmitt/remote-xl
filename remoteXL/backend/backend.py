
from  multiprocessing.connection import Listener
import threading
import json
import logging
import socket
import time

from remoteXL import  main
from remoteXL.util import RepeatTimer
from remoteXL.backend import client_handler,refinement_job,config


class RemoteXLBackend():

    
    def __init__(self):
        self.logger = logging.getLogger(__name__)

        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.listener = self.create_listener()
        self.remote_connections = []
        self.running_jobs = []
        
        self.config = config.Config(self,main.get_config_path())        
        for job_data in self.config.running_jobs:
            job = refinement_job.RefinementJob.from_json(self, job_data)
            self.running_jobs.append(job)
        
        self.save_timer = RepeatTimer(600,self.config._save_config)
        
        
    def run(self):
        self.logger.debug('Backend running')
        self.save_timer.start()

        while not self.stop_event.is_set():
            
            try:
                client_connection = self.listener.accept()
                self.logger.debug("Client_handler started")
                handler = client_handler.ClientHandler(self,client_connection) 
                handler.start()    
            except socket.timeout:
                pass
  
        self.listener.close()
        
        total_timeout = time.time() + 15
        for thread in threading.enumerate():
            if thread == threading.main_thread() or thread.isDaemon():
                continue
            thread.join(timeout=(total_timeout-time.time()))
        if self.save_timer.is_alive():
            self.save_timer.cancel()
        self.config._config_data_changed = True
        self.config._save_config()
        #TODO: Add logging
        
        
    def create_listener(self):
        listener = Listener(('localhost',0))
        port = listener.address[1]
               
            
        listener._listener._socket.settimeout(3)
        return listener           
    
            
    def stop(self):
        self.stop_event.set()      



        