
import sys
import time
import signal
import logging
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow
from PyQt5 import uic

import ctypes
import win32serviceutil

from typing import Type
import traceback
import os
import getpass
from pathlib import Path

from remoteXL import LOGLEVEL, VERSION, remoteXL_service, LOGFORMATSTRING


def get_log_path()  -> str:  
    return r'C:\Users\Manuel\remoteXL.log'


logger = logging.getLogger(__name__)
#fh = logging.FileHandler(Path.home().joinpath(Path(r'remoteXL.log')))
fh = logging.FileHandler(get_log_path())
fh.setFormatter(logging.Formatter(LOGFORMATSTRING))
fh.setLevel(LOGLEVEL)
logger.setLevel(LOGLEVEL)
logger.addHandler(fh)


class ApplicationWindow(QMainWindow):
    def __init__(self):
        super(ApplicationWindow, self).__init__()
        uic.loadUi('../gui/MainWindow.ui', self)  
        self.show()
        



def main():
    
    uic.compileUiDir('../gui')  
    app = QApplication(sys.argv)

    w = ApplicationWindow()
    w.show()
    
    sys.exit(app.exec_())


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False    

                  
def create_crash_report(exc :BaseException) -> str :
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


def my_exception_hook(exctype: Type[BaseException], exc: BaseException, error_traceback) -> None:
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
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

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
            else:
                self.linebuf += line

    def flush(self):
        if self.linebuf != '':
            self.logger.log(self.log_level, self.linebuf.rstrip())
        self.linebuf = ''


if __name__ == '__main__':

    sys.excepthook = my_exception_hook
    logger.info('remoteXL started. Sys.args: ' + str(sys.argv))    
    logger.debug('USER: '+str(getpass.getuser()))
    logger.debug('HOME: '+ str(Path.home()))
    logger.debug('CWD: '+str(os.getcwd()))
   
    if '--backgroundStart' in sys.argv: 
        #Need admin privileges to install or start service  
        if is_admin():   
            
            logger.debug('IS ADMIN')
            #Running in separate admin shell without window -> Redirect stdout and stderr to log file
            sys.stdout = StreamToLogger(logger, logging.DEBUG)
            sys.stderr = StreamToLogger(logger, logging.WARNING)          
            
                
            return_code = win32serviceutil.HandleCommandLine(remoteXL_service.RemoteXLService,argv=[sys.argv[0],'install'])  
            if return_code != 0:
                logger.error('Could not install remoteXL Service. Error: ' +str(return_code))
                sys.exit(1)
                
            return_code = win32serviceutil.HandleCommandLine(remoteXL_service.RemoteXLService,argv=[sys.argv[0],'start'])
            if return_code != 0:
                logger.error('Could not start remoteXL Service. Error: ' + str(return_code))
                sys.exit(1)            
                
            logger.info('remoteXL Service started')
            sys.exit(0)
        else:
            logger.error('Error: Admin privileges are needed to start background service')
            sys.exit(1)

        
    #Re-run the program with admin rights in separate shell
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join([sys.argv[0],'--backgroundStart']), None, 0)
    
    

