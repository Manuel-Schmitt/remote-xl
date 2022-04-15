
from  multiprocessing.connection import Connection, Listener
import threading
import time
import json
import logging
import os
import socket


from remoteXL import  main
from remoteXL.backend import config, client_handler,refinement_job

import subprocess
import sys

class RemoteXLBackend():

    
    def __init__(self):
        self.logger = logging.getLogger(__name__)

        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.listener = self.create_listener()
        self.remote_connections = list()
        self.running_jobs = list()
        
        self.config = config.Config(self,main.get_backendconfig_path())        
        for job_data in self.config.running_jobs:
            job = refinement_job.RefinementJob.from_json(self, job_data)
            self.running_jobs.append(job)
        
        
    def run(self):
        self.logger.debug('Backend running')
        
        threads = list()
        while not self.stop_event.is_set():
            
            try:
                client_connection = self.listener.accept()
                self.logger.debug("Client_handler started")
                #TODO: Maybe implement ClientHandler with multiprocessing instead of Thread?
                handler = client_handler.ClientHandler(self,client_connection) 
                handler.start()    
                threads.append(handler)
            except socket.timeout:
                pass
            
        self.listener.close()
        #TODO: Add wait for threads
        self.config._save_config()
        
    def create_listener(self):
        listener = Listener(('localhost',0))
        port = listener.address[1]
       
        dir = os.path.dirname(main.get_port_path())
        if not os.path.exists(dir):
            os.makedirs(dir)
        
        with open(main.get_port_path(), "w") as jsonfile:
            json.dump({'port':port}, jsonfile,)    
            
        listener._listener._socket.settimeout(3)
        return listener           
    
                    

    
            
    def stop(self):
         self.stop_event.set()      


        