
import sys
import time
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
    _svc_description_ = "Background Process of remoteXL for file synchronization"
           
    def __init__(self, args):
        
        try:
            win32serviceutil.ServiceFramework.__init__(self, args)
                                  
            fh = logging.FileHandler(main.get_log_path(True))
            fh.setFormatter(logging.Formatter(LOGFORMATSTRING))
            fh.setLevel(LOGLEVEL)
            self.logger = logging.getLogger('remoteXL')
            self.logger.setLevel(LOGLEVEL)
            self.logger.addHandler(fh)      
            
            #TODO: Improve
            self.paramiko_logger = logging.getLogger('paramiko')
            self.paramiko_logger.setLevel(LOGLEVEL)
            self.paramiko_logger.addHandler(fh)    
            
            
            self.logger.debug('remoteXL-Service V{}: Initialized'.format(VERSION) )
            self.logger.debug('CWD: '+str(os.getcwd()))
            self.logger.debug('USER: '+str(getpass.getuser()))
            self.logger.debug('HOME: '+ str(Path.home()))
            #Service has no console -> redirect to log
            sys.stdout = main.StreamToLogger(self.logger, logging.DEBUG)
            sys.stderr = main.StreamToLogger(self.logger, logging.WARNING)
            
            
            
        except BaseException as exc:
            self.logger.error(main.create_crash_report(exc))
            raise exc
        
        

    def SvcStop(self):
        try:
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self.backend.stop()
            #TODO Implement soft stop
            #
        except BaseException as exc:
            self.logger.error(main.create_crash_report(exc))
            raise exc
        
     

    def SvcDoRun(self):
        try:
            self.ReportServiceStatus(win32service.SERVICE_START_PENDING)
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            self.logger.info('remoteXL-Service V{}: Running'.format(VERSION) )
            
        
            self.backend = backend.RemoteXLBackend()
            self.backend.run()
            
            self.ReportServiceStatus(win32service.SERVICE_STOPPED)    
                
        except BaseException as exc:
            self.logger.error(main.create_crash_report(exc))
            raise exc           


