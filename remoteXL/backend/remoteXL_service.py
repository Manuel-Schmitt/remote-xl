
import sys
import logging
import os
import getpass
from pathlib import Path

import win32service
import win32serviceutil

from remoteXL import VERSION,LOGLEVEL,LOGFORMATSTRING, main
from remoteXL.backend import backend
    
class RemoteXLService(win32serviceutil.ServiceFramework):
    _svc_name_ = "remoteXL-Service"
    _svc_display_name_ = "remoteXL-Service-V{}".format(VERSION)
    _svc_description_ = "Background process of remoteXL for file synchronization"
    _exe_args_ = "--Service-Call"
           
    def __init__(self, args):
        
        self.backend = None
        
        self.logger = logging.getLogger('remoteXL')
        self.logger.setLevel(LOGLEVEL)
        fh = logging.FileHandler(main.get_log_path(True))
        fh.setFormatter(logging.Formatter(LOGFORMATSTRING))
        fh.setLevel(LOGLEVEL)
        self.logger.addHandler(fh)      
               
        #TODO: Improve
        self.paramiko_logger = logging.getLogger('paramiko')
        self.paramiko_logger.setLevel(LOGLEVEL)
        self.paramiko_logger.addHandler(fh)    
        
        
        self.logger.debug('remoteXL-Service V%s: Initialized',str(VERSION) )
        self.logger.debug('CWD: %s',str(os.getcwd()))
        self.logger.debug('USER: %s',str(getpass.getuser()))
        self.logger.debug('HOME: %s', str(Path.home()))
        #Service has no console -> redirect to log
        sys.stdout = main.StreamToLogger(self.logger, logging.DEBUG)
        sys.stderr = main.StreamToLogger(self.logger, logging.WARNING)
        
        win32serviceutil.ServiceFramework.__init__(self, args)
        
        

    def SvcStop(self):
        try:
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self.backend.stop()
        except BaseException as exc:
            self.logger.error(main.create_crash_report(exc))
            raise exc
        
     

    def SvcDoRun(self):
        try:
            self.ReportServiceStatus(win32service.SERVICE_START_PENDING)  
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            
            self.logger.info('remoteXL-Service V%s: Running',str(VERSION))
            

            self.backend = backend.RemoteXLBackend()
            self.backend.run()
            
            self.ReportServiceStatus(win32service.SERVICE_STOPPED)    
                
        except BaseException as exc:
            self.logger.error(main.create_crash_report(exc))
            raise exc           


