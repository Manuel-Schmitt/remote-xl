
import sys
import time
import logging
import os
import getpass
from pathlib import Path

import win32service
import win32serviceutil

from remoteXL import VERSION,LOGLEVEL,LOGFORMATSTRING, main

    
class RemoteXLService(win32serviceutil.ServiceFramework):
    _svc_name_ = "remoteXL-Service"
    _svc_display_name_ = "remoteXL-Service"
    _svc_description_ = "Background Process of remoteXL for file synchronization"
           
    def __init__(self, args):
        
        try:
            win32serviceutil.ServiceFramework.__init__(self, args)
                                   
            fh = logging.FileHandler(main.get_log_path())
            fh.setFormatter(logging.Formatter(LOGFORMATSTRING))
            fh.setLevel(LOGLEVEL)
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(LOGLEVEL)
            self.logger.addHandler(fh)      
            self.logger.debug('remoteXL-Service: Initialized' )
            self.logger.debug('CWD: '+str(os.getcwd()))
            self.logger.debug('USER: '+str(getpass.getuser()))
            self.logger.debug('HOME: '+ str(Path.home()))
            sys.stdout = main.StreamToLogger(self.logger, logging.DEBUG)
            sys.stderr = main.StreamToLogger(self.logger, logging.WARNING)
            
        except BaseException as exc:
            self.logger.error(main.create_crash_report(exc))
            raise exc
        
        

    def SvcStop(self):
        try:
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            
        except BaseException as exc:
            self.logger.error(main.create_crash_report(exc))
            raise exc
    
     

    def SvcDoRun(self):
        try:
            self.ReportServiceStatus(win32service.SERVICE_START_PENDING)
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            self.logger.info('remoteXL-Service: Running' )
        
            while True:
                with open('C:\\TestService.log', 'a') as f:
                    f.write('test service running...\n'+  str(__name__))
                time.sleep(5)
        except BaseException as exc:
            self.logger.error(main.create_crash_report(exc))
            raise exc           


