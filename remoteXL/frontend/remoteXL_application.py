from PyQt5.QtWidgets import QApplication,QErrorMessage,QMessageBox,QInputDialog,QLineEdit
from PyQt5 import uic

import logging
import socket
import json
import time
from datetime import timedelta 
import os 
import sys
import subprocess

import msvcrt
from win32pipe import PeekNamedPipe

from multiprocessing.connection import Connection 


from remoteXL.frontend.newSetting_window import NewSetting_Window
from remoteXL.frontend.selectSetting_window import SelectSetting_Window, CellWidget, RunningJobDialog
from remoteXL import main

class RemoteXL_Application():
    
    
    def __init__(self,qapp:QApplication):                   
                    
        self.logger = logging.getLogger(__name__)     
        self.timeout = 5  
        self.app = qapp
        self.backend_connection = self.connect_to_backend() 
           
    def authentication(self,setting,parent=None):
        
        pipe_to_agent = None
        pipe_fh = None
        try:
            pipe_to_agent = open(r'\\.\pipe\openssh-ssh-agent', 'rb+', buffering=0)
            pipe_fh = msvcrt.get_osfhandle(pipe_to_agent.fileno())
            self._send(['sshagent',True])    
            self.logger.debug('Connected to ssh-agent')
        except (FileNotFoundError, OSError) as e:  
            self.logger.debug('Ssh-agent not found.')
            self._send(['sshagent',False])  
        
        ok_pressed = True
        while True:
            signal = self._get_data()
            if signal[0] == 'auth':
                should_echo = signal[2]
                if should_echo: 
                    lineEdit = QLineEdit.Normal
                else:
                     lineEdit = QLineEdit.Password
                title = 'Login as {}@{}'.format(setting['user'],setting['host'])
                input, ok_pressed = QInputDialog.getText(parent, title, title+'\n\n'+signal[1],lineEdit)
                if ok_pressed:
                    self._send(['auth',input])
                else:
                    self._send(['auth_cancel'])
            elif signal[0] == 'sshagent-send':
                if pipe_to_agent is not None:
                    pipe_to_agent.write(signal[1])
            elif signal[0] == 'sshagent-recv':  
                data = b'' 
                if pipe_to_agent is not None: 
                    bytes_to_read = signal[1]
                    timeout = time.time() + 2
                    while time.time() < timeout:
                        available_bytes =  PeekNamedPipe(pipe_fh,4)[1]
                        if available_bytes > 0:
                            break
                        time.sleep(0.1)
                    if available_bytes < bytes_to_read:
                        bytes_to_read = available_bytes
                    if bytes_to_read > 0:
                        data = pipe_to_agent.read(bytes_to_read)
                self._send(['sshagent-recv',data])          
                                
            elif signal[0] == 'auth_ok':
                return True
            elif signal[0] == 'auth_error' or signal[0] == 'error':
                #Check ok_pressed here, so no error is displayed if cancel was clicked.
                if ok_pressed:
                    QMessageBox.warning(parent, 'remoteXL: Error', signal[1], QMessageBox.Ok)
                return False
            else:  
                QMessageBox.warning(parent, 'remoteXL: Error', 'Unknown error during authentication', QMessageBox.Ok)
                self.logger.warning('Unknown error during authentication')
                return False

    def runXL(self,setting,parent=None):
        
            start_time = time.time()
            
            if setting['remote']:
                
                response = self.call_backend(['run_refinement',setting])
                success = False
                if response[0] == 'auth_start': 
                    #Increase timeout for authentication, so the backend service stops authentication before the client timeout.
                    self.timeout = 30    
                    success = self.authentication(setting, parent)
                    self.timeout = 5  
                    if not success:
                        return 
                elif response[0] == 'auth_ok': 
                    pass
                elif response[0] == 'error': 
                    #TODO: Add logging after all QMessageBox.warnings
                    QMessageBox.warning(parent, 'remoteXL: Error', response[1], QMessageBox.Ok)
                    self.stop_execution(1)
                else: 
                    QMessageBox.warning(parent, 'remoteXL: Error', 'Unknown signal during refinment start. {}'.format(response[0]), QMessageBox.Ok)
                    self.logger.warning('Unknown signal during refinement start. {}'.format(response[0]))
                    self.stop_execution(1)
                    

                if parent is not None:
                    parent.close()  
                start_time = time.time()
                self.logger.info('Running refinement as {}@{} of {}.'.format(setting['user'],setting['host'],os.path.abspath(sys.argv[1]))) 
                while True:
                    try:
                        data = self.backend_connection.recv()
                        if data[0] == 'shelxl':
                            sys.stdout.write(data[1])
                        if data[0] == 'remoteXL':
                            sys.stdout.write('remoteXL: '+ data[1]+'\n')
                        elif data[0] == 'shelxl_done':
                            break    
                        elif data[0] == 'error': 
                            QMessageBox.warning(None, 'remoteXL: Error', data[1], QMessageBox.Ok)
                            break
                    except (EOFError,ConnectionResetError):    
                        QMessageBox.warning(None, 'remoteXL: Error', 'Unknown error during refinment. See backround service log.', QMessageBox.Ok)
                        self.stop_execution(1)
            else:   
                if parent is not None:
                    parent.close()               
                shelxl = [setting['path']] #contains path to shelxl
                shelxl.extend(sys.argv[1:])
                self.logger.info('Running local refinement of {}'.format(os.path.abspath(sys.argv[1])))  
                self.backend_connection.close()
                cp = subprocess.run(shelxl,stdout=sys.stdout,stderr=sys.stderr)    
                  
            

            run_time = int(time.time() - start_time)
            self.logger.debug("Refinement finished after {}".format(str(timedelta(seconds=run_time)))) 
            
            #Probably not necessary 
            #Ensure that the application exits after running shelxl 
            self.app.quit()   
            
    def exec_(self): 
           
              
        #Check if sys.argv are from ShelXL call 
        #This is the case if sys.argv[1] contains the name of a ins & hkl file
        if len(sys.argv) > 1 :
            ins_hkl_path = os.path.abspath(sys.argv[1])
            if os.path.exists('{}.ins'.format(ins_hkl_path)) and os.path.exists('{}.hkl'.format(ins_hkl_path)):
                signal = ['init_refinement']
                signal.append(ins_hkl_path)
                #Append args for shelxl if available 
                if len(sys.argv) > 2 :
                    signal.append(sys.argv[2:])
            else:     
                QMessageBox.warning(None, 'remoteXL: Error', "One of the following files was not found.\n{}.ins\n{}.res".format(ins_hkl_path,ins_hkl_path), QMessageBox.Ok)
                self.stop_execution(1)
        
        else:
             signal = ['config'] 
       
        response = self.call_backend(signal)

        if response[0] == 'select_setting':
 
            sw = SelectSetting_Window(remoteXLApp=self)
            
           
        elif response[0] == 'running':  
            setting = response[1]
            start_time = response[2]
            
            dialog = RunningJobDialog(setting,start_time )
            dialog.continue_button.clicked.connect(lambda: self.runXL(setting, dialog))
            
        elif response[0] == 'run':
            setting = response[1]
            self.runXL(setting, None)
            self.stop_execution(0)
            
            
        elif response[0] == 'config':
            #TODO implement
            raise NotImplementedError
        elif response[0] == 'error':
            QMessageBox.warning(None, 'remoteXL: Error', response[1], QMessageBox.Ok)
            self.stop_execution(1)
        else:    
            QMessageBox.warning(None, 'remoteXL: Error', "Background service send unknown signal! Restart service and try again.", QMessageBox.Ok)
            self.stop_execution(1)
                        
        return_code = self.app.exec_()
        self.stop_execution(return_code)
    
    def call_backend(self,signal):    
        self._send(signal)
        return self._get_data()

    
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
    
    def _send(self,signal):        
        self.logger.debug('Client signal: {}'.format(signal))
        try: 
            self.backend_connection.send(signal)
        except EOFError:
            self.logger.warning("Connection to background service closed")
            QMessageBox.warning(None, 'remoteXL: Error', "Connection to background service closed!", QMessageBox.Ok)
            self.stop_execution(1)
        except ConnectionResetError as err:
            self.logger.error("Connection to background service interrupted!")
            QMessageBox.warning(None, 'remoteXL: Error', "Connection to background service interrupted!", QMessageBox.Ok)
            self.logger.error(main.create_crash_report(err))
            self.stop_execution(1)
            
    def _get_data(self):
        try: 
            if self.backend_connection.poll(self.timeout):
                data = self.backend_connection.recv()
                return data
            else:
                self.logger.warning('Timeout, when waiting for data from backend!')
                QMessageBox.warning(None, 'remoteXL: Error', "Timeout, when waiting for background service! Restart service and try again.", QMessageBox.Ok)
                self.stop_execution(1)
        except EOFError:
            self.logger.warning("Connection to background service closed")
            QMessageBox.warning(None, 'remoteXL: Error', "Connection to background service closed!", QMessageBox.Ok)
            self.stop_execution(1)
        except ConnectionResetError as err:
            self.logger.error("Connection to background service interrupted!")
            QMessageBox.warning(None, 'remoteXL: Error', "Connection to background service interrupted!", QMessageBox.Ok)
            self.logger.error(main.create_crash_report(err))
            self.stop_execution(1)             
            
    def stop_execution(self,rc=0):
        if not self.backend_connection.closed:
            self.backend_connection.close()
        sys.exit(rc)      
