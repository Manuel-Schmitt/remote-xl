
from  multiprocessing.connection import Connection, Listener
import threading
import time
import json
import logging
import os
import socket
import uuid

from remoteXL import  main
from remoteXL.backend import config
from remoteXL.backend.queingsystems.base_queingsystem import Base_Quingsystem


class RemoteXLBackend():

    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.config = config.Config(main.get_backendconfig_path())
        self.listener = self.create_listener()
        
        
    def run(self):
        self.logger.debug('Backend running')
        
        threads = list()
        while not self.stop_event.is_set():
            
            try:
                client_connection = self.listener.accept()
                self.logger.debug("Client_handler started")
                client_handler = threading.Thread(target=self.handle_client, args=(client_connection,))   
                client_handler.start()    
                threads.append(client_handler)
            except socket.timeout:
                pass
            
        self.listener.close()
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
    
    def handle_client(self,connection:Connection):
        
        def add_connection(data:dict):
            try:
                if data['remote']:
                    cls = Base_Quingsystem.get_subclass_by_name(data['queingsystem']['name'])
                    error = cls.check_settings(data)
                    if error is not None:
                        connection.send(['error',error])
                        return 
                else:
                    if not os.path.exists(data['path']):
                        connection.send(['error','File not found!'])
                        return 
                with self.lock:  
                    if 'id' in data:
                        for index,c in enumerate(self.config.known_connections):
                            if c['id'] == data['id']:
                                self.config.known_connections.remove(c)
                                self.config.known_connections.insert(index, data)
                    else:
                        new_id = uuid.uuid4().int & (1<<16)-1
                        while new_id in self.config.known_connections:
                            new_id = uuid.uuid4().int & (1<<16)-1
                        con = {'id':new_id}
                        con.update(data)      
                        self.config.known_connections.append(con)
                connection.send(['ok'])    
                
                    
                    
                        
            except BaseException as e:
                errorstring = '{}'.format(type(e).__name__)
                connection.send(['error',errorstring])
                raise       
         
            
        try:
            while not self.stop_event.is_set():
            
                #The client sends an initial signal containing a list. 
                #client_signal[1] == refinement for a ShelXL call or client_signal[1} == settings if no sys.args where used when calling remoteXL
                if connection.poll(5):         
                    client_signal =connection.recv()
                else:
                    continue
                
                self.logger.debug("Client signal: {}".format(client_signal))
                
                
                if client_signal[0] == 'refinement':
                    
                    #TODO implement known connections
                    known = "NICHT"
                    if client_signal[1] is known:
                        connection.send(['run'])
                        
                    else:
                        #When no setting is saved for this file, send signal to open connection gui
                        #TODO: Add saved connections
                        connection.send(['select_connection'])
                        
                if client_signal[0] == 'run_connection':
                    pass
                    
                        
                elif client_signal[0] == 'known_connections': 
                    with self.lock:
                        connection.send(self.config.known_connections)  
                        
                elif client_signal[0] == 'queingsystems':   
                     connection.send(Base_Quingsystem.get_all_settings())                  
                          
                elif client_signal[0] == 'new_connection':                      
                     add_connection(client_signal[1])  
                
                elif client_signal[0] == 'edit_connection':                      
                     add_connection(client_signal[1]) 
                elif client_signal[0] == 'delete_connection':
                     conection_id = client_signal[1]['id']                      
                     with self.lock:
                          for c in self.config.known_connections:
                              if c['id'] == conection_id:
                                  self.config.known_connections.remove(c)
                                  break
               
                elif client_signal[0] == 'change_order':   
                    old_position = client_signal[1][0]
                    new_position = client_signal[1][1]
                    with self.lock:
                        con = self.config.known_connections.pop(old_position)
                        self.config.known_connections.insert(new_position, con)
                        
                        
                elif client_signal[0] == 'settings':
                    
                     #TODO implement settings
                    
                    #Return saved setting values 
                    connection.send(['settings'])
                    
                    
                    
                   
                else:    
                    self.logger.warning("Client send unknown initial signal! Close connection!")
                    connection.close()
                    break
                
                
                
                
        except EOFError:
            self.logger.debug("Connection to client closed")
        except ConnectionResetError:
            self.logger.error("Connection to client interrupted!")
            raise
        except Exception:
            self.logger.error("Unknown exception handling client!")
            raise
        finally:
            if not connection.closed:
                connection.close()   
                    

    
            
    def stop(self):
         self.stop_event.set()      


        