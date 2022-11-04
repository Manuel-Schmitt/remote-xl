from PyQt5.QtWidgets import QApplication,QMessageBox,QInputDialog,QLineEdit
from PyQt5.QtCore import QSettings

import logging
import socket
import json
import time
from datetime import timedelta 
import sys
import psutil
import os
import subprocess
from pathlib import Path

import win32api
import win32con
import win32job

import msvcrt
from win32pipe import PeekNamedPipe  #pylint: disable=no-name-in-module

from multiprocessing.connection import Connection 
from multiprocessing import Process


from remoteXL.frontend.selectSetting_window import SelectSetting_Window, RunningJobDialog
from remoteXL.frontend.config_window import Config_Window
from remoteXL import main, REMOTEXL_SERVICE_NAME


class RemoteXL_Application():
    
    
    def __init__(self,qapp:QApplication):                   
                    
        self.logger = logging.getLogger(__name__)     
        self.timeout = 5  
        self.app = qapp
        self.ins_hkl_path = None
        self.backend_connection = self.connect_to_backend() 

    def authentication(self,setting,parent=None):
        
        pipe_to_agent = None
        pipe_fh = None
        try:
            pipe_to_agent = open(r'\\.\pipe\openssh-ssh-agent', 'rb+', buffering=0)
            pipe_fh = msvcrt.get_osfhandle(pipe_to_agent.fileno())
            self._send(['sshagent',True])    
            self.logger.debug('Connected to ssh-agent')
        except (FileNotFoundError, OSError):  
            self.logger.debug('Ssh-agent not found.')
            self._send(['sshagent',False])  
        
        ok_pressed = True
        while True:
            backend_signal = self._get_data()
            if backend_signal[0] == 'auth':
                should_echo = backend_signal[2]
                if should_echo: 
                    lineEdit = QLineEdit.Normal
                else:
                    lineEdit = QLineEdit.Password
                title = 'Login as {}@{}'.format(setting['user'],setting['host'])
                input_text, ok_pressed = QInputDialog.getText(parent, title, title+'\n\n'+backend_signal[1],lineEdit)
                if ok_pressed:
                    self._send(['auth',input_text])
                else:
                    self._send(['auth_cancel'])
            elif backend_signal[0] == 'sshagent-send':
                if pipe_to_agent is not None:
                    pipe_to_agent.write(backend_signal[1])
            elif backend_signal[0] == 'sshagent-recv':  
                data = b'' 
                if pipe_to_agent is not None: 
                    bytes_to_read = backend_signal[1]
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
                                
            elif backend_signal[0] == 'auth_ok':
                return True
            elif backend_signal[0] == 'auth_start':
                continue
            elif backend_signal[0] == 'auth_error' or backend_signal[0] == 'error':
                #Check ok_pressed here, so no error is displayed if cancel was clicked.
                if ok_pressed:
                    QMessageBox.warning(parent, 'remoteXL: Error', backend_signal[1], QMessageBox.Ok)
                    self.logger.warning('Error: %s',backend_signal[1])
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
                QMessageBox.warning(parent, 'remoteXL: Error', response[1], QMessageBox.Ok)
                self.logger.warning('Error: %s',response[1])
                self.stop_execution(1)
            else: 
                QMessageBox.warning(parent, 'remoteXL: Error', 'Unknown signal during refinment start. {}'.format(response[0]), QMessageBox.Ok)
                self.logger.warning('Unknown signal during refinement start. %s',str(response[0]))
                self.stop_execution(1)
                

            if parent is not None:
                parent.close()  
            start_time = time.time()
            self.logger.info('Running refinement as {}@{} of {}.'.format(setting['user'],setting['host'],Path(sys.argv[1]).resolve())) 
            while True:
                try:
                    data = self.backend_connection.recv()
                    if data[0] == 'shelxl':
                        sys.stdout.write(data[1])
                        sys.stdout.flush()
                    if data[0] == 'remoteXL':
                        sys.stdout.write('remoteXL: '+ data[1]+'\n')
                    elif data[0] == 'shelxl_done':
                        break    
                    elif data[0] == 'error': 
                        QMessageBox.warning(None, 'remoteXL: Error', data[1], QMessageBox.Ok)
                        self.logger.warning('Error: %s',data[1])
                        break
                except (EOFError,ConnectionResetError):    
                    QMessageBox.warning(None, 'remoteXL: Error', 'Unknown error during refinement. See background service log.', QMessageBox.Ok)
                    self.logger.warning('Error: Unknown error during refinement. See background service log.')
                    self.stop_execution(1)
        else:   
            if parent is not None:
                parent.close()               
            shelxl_cmd = [setting['path']] #contains path to shelxl
            shelxl_cmd.extend(sys.argv[1:])
            self.logger.info('Running local refinement of %s',str(Path(sys.argv[1]).absolute()))  
            self.backend_connection.close()
 
            
            hJob = win32job.CreateJobObject(None, "")
            extended_info = win32job.QueryInformationJobObject(hJob, win32job.JobObjectExtendedLimitInformation)
            extended_info['BasicLimitInformation']['LimitFlags'] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(hJob, win32job.JobObjectExtendedLimitInformation, extended_info)
            
            CREATE_NO_WINDOW = 0x08000000
            shelxl_process = subprocess.Popen(shelxl_cmd,stdout=sys.stdout,stderr=sys.stderr, creationflags=CREATE_NO_WINDOW)
            # Convert process id to process handle:
            perms = win32con.PROCESS_TERMINATE | win32con.PROCESS_SET_QUOTA
            hProcess = win32api.OpenProcess(perms, False, shelxl_process.pid)

            win32job.AssignProcessToJobObject(hJob, hProcess)
            
            shelxl_process.wait()
        

        run_time = int(time.time() - start_time)
        self.logger.debug("Refinement finished after %s",str(timedelta(seconds=run_time))) 
        
        #Probably not necessary 
        #Ensure that the application exits after running shelxl 
        self.app.quit()   
            
    def exec_(self): 
        

        parent_process = psutil.Process(os.getpid()).parent()
        if 'shelxle' in parent_process.name().lower():
            self.check_shelxle_integration() 
            response =   self.call_backend(['add_pids',os.getpid(),parent_process.pid])
            if response[0] == 'error': 
                QMessageBox.warning(None, 'remoteXL: Error', response[1], QMessageBox.Ok)
                self.logger.warning('Error: %s',response[1])
        
        #Check if sys.argv are from ShelXL call 
        #This is the case if sys.argv[1] contains the name of a ins & hkl file
        argv = sys.argv.copy()
        if '-config' in argv:
            init_signal = ['config'] 
            argv.remove('-config')
        elif '--config' in argv:
            init_signal = ['config'] 
            argv.remove('--config')
        elif len(argv) == 1:
            init_signal = ['config'] 
        else:
            init_signal = ['init_refinement']
            
        
        if len(argv) > 1 :
            self.ins_hkl_path = Path(argv[1]).absolute()
            if self.ins_hkl_path.with_suffix('.ins').is_file() and self.ins_hkl_path.with_suffix('.hkl').is_file():

                init_signal.append(str(self.ins_hkl_path))
                #Append args for shelxl if available 
                if len(argv) > 2 :
                    init_signal.append(argv[2:])
            else:     
                QMessageBox.warning(None, 'remoteXL: Error', "One of the following files was not found.\n{p}.ins\n{p}.res".format(p=self.ins_hkl_path), QMessageBox.Ok)
                self.logger.warning("Error: One of the following files was not found.\n%s.ins\n%s.res",str(self.ins_hkl_path),str(self.ins_hkl_path))
                self.stop_execution(1)
            
        response = self.call_backend(init_signal)

        if response[0] == 'select_setting':

            sw = SelectSetting_Window(remoteXLApp=self)  #pylint: disable=unused-variable
            
           
        elif response[0] == 'running':  
            setting = response[1]
            start_time = response[2]
            ins_changed = response[3]
            dialog = RunningJobDialog(setting,start_time,ins_changed,lambda: self.runXL(setting),self.stop_refinement)  #pylint: disable=unused-variable
            
            
        elif response[0] == 'run':
            setting = response[1]
            self.runXL(setting, None)
            self.stop_execution(0)
            
            
        elif response[0] == 'config':
            config_data = response[1]
            cw = Config_Window(config_data,self.ins_hkl_path,remoteXLApp=self)  #pylint: disable=unused-variable
        elif response[0] == 'error':
            QMessageBox.warning(None, 'remoteXL: Error', response[1], QMessageBox.Ok)
            self.logger.warning('Error: %s',response[1])
            self.stop_execution(1)
        else:    
            QMessageBox.warning(None, 'remoteXL: Error', "Background service send unknown signal! Restart service and try again.", QMessageBox.Ok)
            self.logger.warning("Error: Background service send unknown signal! Restart service and try again.")
            self.stop_execution(1)
                        
        return_code = self.app.exec_()
        self.stop_execution(return_code)
    
    
    def call_backend(self,signal):    
        self._send(signal)
        return self._get_data()
    
    
    
    def connect_to_backend(self):
        s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        
        #Find backend process port
        backend_port = None
        backend_pid = psutil.win_service_get(REMOTEXL_SERVICE_NAME).pid()
        backend_process = psutil.Process(backend_pid)
        
        for con in backend_process.connections():
            if con.laddr.ip == '127.0.0.1' or con.laddr.ip == 'localhost':
                if con.status == psutil.CONN_LISTEN:
                    backend_port = con.laddr.port

               
        
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
        if not signal[0] == 'auth' and not signal[0] == 'sshagent-recv' :   
            self.logger.debug('Client signal: %s',str(signal))
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
       
    def stop_refinement(self):
        response = self.call_backend(['kill_job'])
        if response[0] == 'ok':
            sw = SelectSetting_Window(remoteXLApp=self)  #pylint: disable=unused-variable
        elif response[0] == 'error':
            QMessageBox.warning(None, 'remoteXL: Error', response[1], QMessageBox.Ok)
            self.logger.warning('Error: %s',response[1])
     
    def stop_execution(self,rc=0):
        if not self.backend_connection.closed:
            self.backend_connection.close()
        sys.exit(rc)      
    
          
        


    def check_shelxle_integration(self):
        
        if not getattr(sys, 'frozen', False):
            return
        
        
        shelxle_config_parent_dir = Path(os.getenv('APPDATA')) / 'shelXle'
        all_config_files = shelxle_config_parent_dir.glob('shelXle*.ini')
        #Different shelXle versions use different config files, however the latest changed file has to belong to the currently running version
        config_file_path = max(all_config_files,key=os.path.getmtime)
        
        #remoteXL is added to the 'Extra' block of the shelXle config file
        
        class External_Programm():
            setting_dict = {
                'ProgramNames':'Name',
                'ProgramPaths':'Path',
                'AlternativeExtensions':'ext',
                'CommandLineOptions':'opt',
                'ProgramArgs':'Arg',
                'ProgramExtensions':'Ext',
                'ProgramResIns':'Res2Ins',
                'FileDialog':'fd',
                'IconOverlay':'icov',
                'OverlayPointSize':'icov',
                'AltExtraIconPaths':'altIcon',
                'ProgramDetached':'Detach',
                }
            def __init__(self,attr_dict=None):
                if attr_dict is not None:
                    for key,value in attr_dict.items():
                        self.__setattr__(key,value)
                        
        remoteXL_setting_dict = {
                'ProgramNames':'remoteXL',
                'ProgramPaths':Path(sys.executable).as_posix(),
                'AlternativeExtensions':'',
                'CommandLineOptions':'--config',
                'ProgramArgs':'2',
                'ProgramExtensions':'2',
                'ProgramResIns':'2',
                'FileDialog':'0',
                'IconOverlay':'0',
                'OverlayPointSize':'36',
                'AltExtraIconPaths':'',
                'ProgramDetached':'2',
                }
        
        def read_config(config):
            
            config.beginGroup('Extra')
            size = config.beginReadArray('ProgramNames')
            config.endArray()
            programm_list = [External_Programm() for i in range(size)]
            
            for key,value in External_Programm.setting_dict.items():
                config.beginReadArray(key)
                for i in range(size):
                    config.setArrayIndex(i)
                    programm_list[i].__setattr__(key,config.value(value))
                config.endArray()
            config.endGroup()
        
            
            return programm_list
        
        
        def write_config(programm_list,config):

            config.beginGroup('Extra')
            size = len(programm_list)
            
            for key,value in External_Programm.setting_dict.items():
                config.beginWriteArray(key)
                for i in range(size):
                    config.setArrayIndex(i)
                    config.setValue(value,programm_list[i].__getattribute__(key))
                config.endArray()
            config.endGroup()
            config.sync()
        
        
        
        config = QSettings(QSettings.IniFormat,QSettings.UserScope,'shelxle',config_file_path.stem)
        programm_list = read_config(config)
           
        for programm in programm_list:
            if programm.ProgramNames == 'remoteXL':
                return
        
        response = QMessageBox.question(None, 'remoteXL','Should remoteXL be integrated in shelXle as an external program?', QMessageBox.No|QMessageBox.Yes) 
        if response == QMessageBox.Yes: 
            programm_list.append(External_Programm(remoteXL_setting_dict))
            write_config(programm_list,config)
            QMessageBox.information(None, 'remoteXL','ShelXle must be restarted for the changes to take effect.', QMessageBox.Ok) 
            self.stop_execution(0)
        
       