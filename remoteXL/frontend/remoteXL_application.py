from PyQt5.QtWidgets import QApplication,QErrorMessage,QMessageBox
from PyQt5.QtCore import QCoreApplication
from PyQt5 import uic

import logging
import socket
import json
import time
import os 
import sys
import subprocess

from multiprocessing.connection import Connection 

from PyQt5.QtWidgets import QApplication

from remoteXL.frontend.newConnection_window import NewConnection_Window
from remoteXL.frontend.selectConnection_window import SelectConnection_Window
from remoteXL import main

class RemoteXL_Application():
    
    
    def __init__(self,qapp:QApplication):
    
        self.logger = logging.getLogger(__name__) 
        
        self.timeout = 5  
        self.app = qapp
        self.backend_connection = self.connect_to_backend() 
            

        #uic.compileUiDir('gui') 
    def runXL(self,connection):
            if connection['remote']:
                raise NotImplementedError
                response = self.call_backend('')
                for line in self.backend_connection.recv():
                    print(line)

            else:   
                shelxl = [connection['path']] #contains path to shelxl
                shelxl.extend(sys.argv[1:])
                self.logger.info('Running refinement: {} in {}'.format(shelxl,os.getcwd()))  
                cp = subprocess.run(shelxl,stdout=sys.stdout,stderr=sys.stderr)    

    def exec_(self): 
        return_code = 0   
              
        #Check if sys.argv are from ShelXL call 
        #This is the case if sys.argv[1] contains the name of a ins & hkl file
        if len(sys.argv) > 1 :
            if os.path.exists('{}.ins'.format(sys.argv[1])) and os.path.exists('{}.hkl'.format(sys.argv[1])):
                signal = ['refinement']
                signal.append(os.path.abspath(sys.argv[1]))
                if len(sys.argv) > 2 :
                    signal.append(sys.argv[2:])
            else:
               
                QMessageBox.warning(None, 'remoteXL: Error', "One of the following files not found.\n{}.ins\n{}.res".format(sys.argv[1],sys.argv[1]), QMessageBox.Ok)
                self.backend_connection.close()
                return 1
        
        else:
             signal = ['settings'] 
       
             
        response = self.call_backend(signal)

        if response[0] == 'select_connection':
 
            sw = SelectConnection_Window(remoteXLApp=self)
            
            #TODO: Process saved connections  
        elif response[0] == 'run':    
            #TODO implement
            raise NotImplementedError
        elif response[0] == 'settings':
            #TODO implement
            raise NotImplementedError
        else:    
            QMessageBox.warning(None, 'remoteXL: Error', "Background service send unknown signal! Restart service and try again.", QMessageBox.Ok)
            self.stop_execution(1)
                        
        return_code = self.app.exec_()
        self.stop_execution(return_code)
    
    def call_backend(self,signal):
        try: 
            self.backend_connection.send(signal)
            return self._get_data()
        except EOFError:
            self.logger.warning("Connection to background service closed")
            QMessageBox.warning(None, 'remoteXL: Error', "Connection to background service closed!", QMessageBox.Ok)
            self.stop_execution(1)
        except ConnectionResetError as err:
            self.logger.error("Connection to background service interrupted!")
            QMessageBox.warning(None, 'remoteXL: Error', "Connection to background service interrupted!", QMessageBox.Ok)
            self.logger.error(main.create_crash_report(err))
            self.stop_execution(1)
    
    def connect_to_backend(self):
        s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        with open(main.get_port_path(), "r") as jsonfile:
            port_dict = json.load(jsonfile)
        backend_port = port_dict['port']
        s.settimeout(self.timeout)
        try: 
            s.connect(('localhost',backend_port))          
        except socket.timeout:
            self.logger.warning('Timeout, when connecting to backend!')
            QMessageBox.warning(None, 'remoteXL: Error', "Timeout, when waiting for background service! Restart service and try again.", QMessageBox.Ok)
            self.stop_execution(1)
        s.setblocking(True)
        connection = Connection(s.detach())
        self.logger.debug("Client connected to backend")    
        return connection    
            
            
    def _get_data(self):
        if self.backend_connection.poll(self.timeout):
            data = self.backend_connection.recv()
            return data
        else:
            self.logger.warning('Timeout, when waiting for data from backend!')
            QMessageBox.warning(None, 'remoteXL: Error', "Timeout, when waiting for background service! Restart service and try again.", QMessageBox.Ok)
            self.stop_execution(1)
                     
            
    def stop_execution(self,rc=0):
        if not self.backend_connection.closed:
            self.backend_connection.close()
        sys.exit(rc)      
