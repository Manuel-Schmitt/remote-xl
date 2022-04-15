
import sys
import time
import signal
import logging
from pathlib import Path


import ctypes
import win32serviceutil
import win32service, pywintypes


from typing import Type
import traceback
import os
import getpass
from pathlib import Path
import psutil

from PyQt5.QtWidgets import QApplication,QMessageBox


from remoteXL import LOGLEVEL, VERSION, LOGFORMATSTRING
from remoteXL.backend import remoteXL_service
from remoteXL.frontend.remoteXL_application import RemoteXL_Application

def get_log_path(is_service=False)  -> str:  
    #TODO update
    
    if is_service:
        return r'C:\Users\Manuel\remoteXL-backend.log'
    
    return r'C:\Users\Manuel\remoteXL.log'
    
    
    
    if is_service:
       return os.environ['ALLUSERSPROFILE']+r'\remoteXL\remoteXL_service.log' 
    return os.environ['ALLUSERSPROFILE']+r'\remoteXL\remoteXL_client.log'
def get_port_path()  -> str:  
    #TODO update
    return os.environ['ALLUSERSPROFILE']+r'\remoteXL\port'
def get_backendconfig_path()  -> str:  
    #TODO update
    return os.environ['ALLUSERSPROFILE']+r'\remoteXL\remoteXL.config'
def get_config_path()  -> str:  
    #TODO update
    return os.environ['APPDATA']+r'\remoteXL\remoteXL.config'

    



def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False    
                  
def create_crash_report(exc:BaseException) -> str :
    errortext = 'remoteXL V{} crash report:\n'.format(VERSION)
    errortext += 'Python ' + sys.version + '\n'
    errortext += 'System: '+ sys.platform + '\n'
    errortext += time.asctime(time.localtime(time.time())) + '\n'
    errortext += '-' * 80 + '\n'
    errortext += ''.join(traceback.format_tb(exc.__traceback__)) + '\n'
    errortext += str(type(exc).__name__) + ': '
    errortext += str(exc) + '\n'
    errortext += '-' * 80 + '\n'    
    return errortext


def my_exception_hook(exctype:Type[BaseException], exc:BaseException, error_traceback) -> None:
    """
    Hook to create debug reports.
    """
    logger.error(create_crash_report(exc))       
    sys.__excepthook__(exctype, exc, error_traceback)
    sys.exit(1)
    
class StreamToLogger(object):
    """
    Fake file-like stream object that redirects writes to a logger instance.
    """
    def __init__(self, logger, log_level=logging.INFO,old_out=None):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''
        self.old_out = old_out

    def write(self, buf):
        temp_linebuf = self.linebuf + buf
        self.linebuf = ''
        for line in temp_linebuf.splitlines(True):
            # From the io.TextIOWrapper docs:
            #   On output, if newline is None, any '\n' characters written
            #   are translated to the system default line separator.
            # By default sys.stdout.write() expects '\n' newlines and then
            # translates them so this is still cross platform.
            if line[-1] == '\n':
                self.logger.log(self.log_level, line.rstrip())
                if self.old_out is not None: 
                    self.old_out.write(line)
            else:
                self.linebuf += line

    def flush(self):
        if self.linebuf != '':
            self.logger.log(self.log_level, self.linebuf.rstrip())
            if self.old_out is not None: 
                self.old_out.flush()
        self.linebuf = ''

def run_service_command(commands:list) ->None:
    commands.insert(0, sys.argv[0] )
    #This code should only run in separate admin shell without window -> Copy stdout and stderr to log file
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = StreamToLogger(logger, logging.DEBUG,sys.stdout)
    sys.stderr = StreamToLogger(logger, logging.WARNING,sys.stderr) 
    return_code = win32serviceutil.HandleCommandLine(remoteXL_service.RemoteXLService,argv=commands)     
    if return_code != 0:
        logger.error('Could not {} remoteXL Service. Error: '.format(str(commands)) +str(return_code))
        sys.exit(1)
    #Restore original stdout
    sys.stdout, sys.stderr = original_stdout, original_stderr
   
def wait_for_service_status(*status,timeout=10):
    timeout_start = time.time()
    while time.time() < timeout_start + timeout:
        try:       
            service_status = win32serviceutil.QueryServiceStatus(remoteXL_service.RemoteXLService._svc_name_)[1]
            if service_status in status:
                logger.debug('remoteXL Service status: {}'.format(service_status))
                return
        except pywintypes.error as err:
            #remoteXL-Service not installed
            pass
        time.sleep(0.5) 
    logger.error('remoteXL Service is not responding! Status: {}'.format(service_status))  
    QMessageBox.warning(None, 'remoteXL: Error','RemoteXL service is not responding! Try to restart the service', QMessageBox.Ok) 
    sys.exit(1)
    
def wait_for_children():
    try:
        own_process = psutil.Process(os.getpid())
        children = own_process.children()
        for c in children:
            if c.name == 'python.exe': 
                c.wait(timeout=10)     
    except psutil.NoSuchProcess:
        return
    except psutil.TimeoutExpired:
        logger.error('Timeout when waiting for remoteXL service!')  
        QMessageBox.error(None, 'remoteXL: Error','Timeout when waiting for remoteXL service!', QMessageBox.Ok) 
        sys.exit(1)
       
    
def check_service():
    service_running = False
    service_installed = True
    try:       
        wait_for_service_status(win32service.SERVICE_STOPPED,win32service.SERVICE_RUNNING)
        service_status = win32serviceutil.QueryServiceStatus(remoteXL_service.RemoteXLService._svc_name_)[1]
        if service_status == win32service.SERVICE_STOPPED:
            logger.info('remoteXL Service is not running')
        elif service_status == win32service.SERVICE_RUNNING:
            logger.debug('remoteXL Service is running.') 
            service_running = True   
    except pywintypes.error as err:
        #remoteXL-Service not installed
        service_installed = False
   
   
    if '--StartService' in sys.argv: 
        #Need admin privileges to install or start service  
        if is_admin():                     
            run_service_command(['start'])                         
            logger.info('remoteXL Service started')
            sys.exit(0)
        else:
            logger.error('Error: Admin privileges are needed to change remoteXL service')
            sys.exit(1)
            
            
    if '--InstallService' in sys.argv:
        #Need admin privileges to install or start service  
        if is_admin():  
            if service_running:
                run_service_command(['stop'])
                wait_for_service_status(win32service.SERVICE_STOPPED)
                logger.info('remoteXL Service stopped')
            run_service_command(['--startup=auto','install'])
            logger.info('remoteXL Service installed')
            run_service_command(['start'])                         
            logger.info('remoteXL Service started')
            sys.exit(0)          
        else:
            logger.error('Error: Admin privileges are needed to change remoteXL service')
            sys.exit(1)
            
    if '--UpdateService' in sys.argv:
        #Need admin privileges to install or start service  
        if is_admin(): 
            if service_running:
                run_service_command(['stop'])
                wait_for_service_status(win32service.SERVICE_STOPPED)
                logger.info('remoteXL Service stopped')
            run_service_command(['--startup=auto','update'])
            logger.info('remoteXL Service updated')
            run_service_command(['start'])                         
            logger.info('remoteXL Service started')
            sys.exit(0)          
        else:
            logger.error('Error: Admin privileges are needed to change remoteXL service')
            sys.exit(1)
    if '--RemoveService' in sys.argv:
        #Need admin privileges to install or start service  
        if is_admin():  
            if service_running:
                run_service_command(['stop'])
                wait_for_service_status(win32service.SERVICE_STOPPED)
                logger.info('remoteXL Service stopped')
            run_service_command(['remove'])
            logger.info('remoteXL Service removed')
            sys.exit(0)          
        else:
            logger.error('Error: Admin privileges are needed to change remoteXL service')
            sys.exit(1)
            
    if '--StopService' in sys.argv:
        #Need admin privileges to install or start service  
        if is_admin():  
            run_service_command(['stop'])
            wait_for_service_status(win32service.SERVICE_STOPPED)
            logger.info('remoteXL Service stopped')
            sys.exit(0)          
        else:
            logger.error('Error: Admin privileges are needed to change remoteXL service')
            sys.exit(1)
     
    if not service_installed:   
        #Re-run the program with admin rights in separate shell to install and start service
        #TODO: Add more info and add integration into shelxle
        response = QMessageBox.question(None, 'remoteXL','RemoteXL background service is not running.\nAdministrator rights are required to continue.', QMessageBox.Cancel|QMessageBox.Ok) 
        if response == QMessageBox.Ok:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join([sys.argv[0],'--InstallService']), None, 0)
            wait_for_children()
            wait_for_service_status(win32service.SERVICE_RUNNING)
            return
        else:
            logger.warning('Installation canceled!')
            sys.exit(1)
           

    #Get version of installed remoteXL service from display name
    try:
        hscm = win32service.OpenSCManager(None, None, 1 )
        hs = win32service.OpenService(hscm, remoteXL_service.RemoteXLService._svc_name_, win32service.SERVICE_QUERY_CONFIG )
        try:
            service_config = win32service.QueryServiceConfig(hs)
            display_name = str(service_config[8])
            installed_version = display_name.replace('remoteXL-Service-V','').strip()
        finally:
            win32service.CloseServiceHandle(hs)
    except win32service.error as err:
         logger.warning('Could not get version of installed remoteXL service! Continue...') 
    finally:
        win32service.CloseServiceHandle(hscm)


    if installed_version is not None:
        logger.debug('remoteXL-Service V{} is installed'.format(installed_version))      
        if installed_version != str(VERSION):
            #Re-run the program with admin rights in separate shell to update and start service
            logger.warning('remoteXL-Service V{} is out of date. Updating to V{}'.format(installed_version,VERSION))  
            response = QMessageBox.question(None, 'remoteXL','RemoteXL background service is out of date.\nAdministrator rights are required to continue.', QMessageBox.Cancel|QMessageBox.Ok) 
            if response == QMessageBox.Ok:
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join([sys.argv[0],'--UpdateService']), None, 0)
                wait_for_children()
                wait_for_service_status(win32service.SERVICE_RUNNING)
                return 
            else:
                logger.warning('Update canceled!')
                sys.exit(1)
                
    if not service_running:     
        #Re-run the program with admin rights in separate shell to start service
        response = QMessageBox.question(None, 'remoteXL','RemoteXL background service is not running.\nAdministrator rights are required to continue.', QMessageBox.Cancel|QMessageBox.Ok) 
        if response == QMessageBox.Ok:    
            #TODO: RMEOVE
            #ALWAYS UPDATE
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join([sys.argv[0],'--UpdateService']), None, 0)
            #ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join([sys.argv[0],'--StartService']), None, 0)       
            wait_for_children()
            wait_for_service_status(win32service.SERVICE_RUNNING)
        else:
            logger.warning('Start of background service canceled!')
            sys.exit(1)
            
if __name__ == '__main__':
    
    logger = logging.getLogger('remoteXL')

    #fh = logging.FileHandler(Path.home().joinpath(Path(r'remoteXL.log')))
    fh = logging.FileHandler(get_log_path())
    fh.setFormatter(logging.Formatter(LOGFORMATSTRING))
    fh.setLevel(LOGLEVEL)
    logger.setLevel(LOGLEVEL)
    logger.addHandler(fh)

    sys.excepthook = my_exception_hook
    logger.info('remoteXL started. Sys.args: ' + str(sys.argv))    
    logger.debug('USER: '+str(getpass.getuser()))
    logger.debug('HOME: '+ str(Path.home()))
    logger.debug('CWD: '+str(os.getcwd()))
    logger.debug('Is Admin? '+str(is_admin()))
   



    
    qapp = QApplication([])
   
    check_service()
    
    app = RemoteXL_Application(qapp)
    app.exec_()
    

