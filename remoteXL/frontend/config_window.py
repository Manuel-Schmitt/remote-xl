import logging
from datetime import datetime

from PyQt5.QtWidgets import QMainWindow, QPushButton,QWidget, QLabel,QHBoxLayout,QGridLayout, QVBoxLayout,QDialog,QMessageBox
from PyQt5.QtGui import  QFont
from PyQt5 import Qt

from remoteXL.gui.Ui_Config_Window import Ui_Config_Window
from remoteXL.gui.Ui_NewConnection_Window import Ui_NewConnection_Window
from remoteXL.frontend.selectDefault_window import SelectDefault_Window


class Config_Window(QMainWindow):
    def __init__(self,config_data,ins_hkl_path,remoteXLApp):
        super().__init__()   
        self.config_data = config_data 
        self.ins_hkl_path = ins_hkl_path
        self.remoteXLApp = remoteXLApp
        self.logger = logging.getLogger(__name__)
        self.ui = Ui_Config_Window()
        self.ui.setupUi(self)
        self.setWindowTitle("remoteXL")    
        
        self.ui.connection_tableWidget.verticalHeader().setSectionResizeMode(Qt.QHeaderView.Fixed)
        self.ui.connection_tableWidget.verticalHeader().setSectionsMovable(False)
        self.ui.jobs_tableWidget.verticalHeader().setSectionResizeMode(Qt.QHeaderView.Fixed)
        self.ui.jobs_tableWidget.verticalHeader().setSectionsMovable(False)
        
        if self.remoteXLApp.ins_hkl_path is None:
            self.ui.file_defaults_pushButton.hide()
            self.ui.file_defaults_label.hide()
        
        self.ui.global_defaults_pushButton.clicked.connect(self.global_defaults_pressed)
        self.ui.file_defaults_pushButton.clicked.connect(self.file_defaults_pressed)
        self.ui.stop_pushButton.clicked.connect(self.stop_pressed)
        self.ui.refresh_pushButton.clicked.connect(self.refresh_pressed)
        self.ui.disconnect_pushButton.clicked.connect(self.disconnect_pressed)
        self.ui.connect_pushButton.clicked.connect(self.connect_pressed)
        
        self.set_connection_table()
        self.set_job_table()
        self.show()
        
        
    def set_connection_table(self):
        self.ui.connection_tableWidget.setRowCount(0)
        connections = self.config_data['connections']
        self.ui.connection_tableWidget.setRowCount(len(connections))   
        for idx,con in enumerate(connections):            
            cw = ConnectionWidget(con)
            self.ui.connection_tableWidget.setCellWidget(idx,0,cw)
            self.ui.connection_tableWidget.setRowHeight(idx, cw.height() )
        
        
    def set_job_table(self):   
        self.ui.jobs_tableWidget.setRowCount(0)
        jobs = self.config_data['running_jobs']
        self.ui.jobs_tableWidget.setRowCount(len(jobs))   
        
        for idx,job in enumerate(jobs):            
            jw = JobWidget(job)
            self.ui.jobs_tableWidget.setCellWidget(idx,0,jw)
            self.ui.jobs_tableWidget.setRowHeight(idx, jw.height() )
            
        
    def global_defaults_pressed(self):
        SelectDefault_Window(self.remoteXLApp,True,self)
    def file_defaults_pressed(self):
        SelectDefault_Window(self.remoteXLApp,False,self)
    
    def stop_pressed(self):
        row = self.ui.jobs_tableWidget.currentRow()       
        if row == -1:
            return 
        
        selected_job = self.ui.jobs_tableWidget.cellWidget(row, 0).job
         
        response = self.remoteXLApp.call_backend(['kill_job',selected_job['local_file']])
        if response[0] == 'ok':
            pass
        elif response[0] == 'error':
            QMessageBox.warning(self, 'remoteXL: Error', response[1], QMessageBox.Ok)
            self.logger.warning('Error: %s',response[1])
        else: 
            QMessageBox.warning(self, 'remoteXL: Error', "Background service send unknown signal! Restart service and try again.", QMessageBox.Ok)
            self.logger.warning("Error: Background service send unknown signal! Restart service and try again.")
        
        self.refresh_pressed()  

    def connect_pressed(self):
        NewConnection_Window(self)
          
        
        
    def disconnect_pressed(self):
        row = self.ui.connection_tableWidget.currentRow()       
        if row == -1:
            return 
        connection = self.ui.connection_tableWidget.cellWidget(row, 0).connection  
                    
        response = self.remoteXLApp.call_backend(['disconnect',connection])
        
        if response[0] == 'ok':
            pass
        elif response[0] == 'error':
            QMessageBox.warning(self, 'remoteXL: Error', response[1], QMessageBox.Ok)
            self.logger.warning('Error: %s',response[1])
        else: 
            QMessageBox.warning(self, 'remoteXL: Error', "Background service send unknown signal! Restart service and try again.", QMessageBox.Ok)
            self.logger.warning("Error: Background service send unknown signal! Restart service and try again.")
        
        self.refresh_pressed()
   
    def refresh_pressed(self):
        self.ui.refresh_pushButton.setDisabled(True)
        response = self.remoteXLApp.call_backend(['config'])
        self.ui.refresh_pushButton.setDisabled(False)
        if response[0] == 'config':
            self.config_data = response[1]
            self.set_connection_table()
            self.set_job_table()
        elif response[0] == 'error':
            QMessageBox.warning(self, 'remoteXL: Error', response[1], QMessageBox.Ok)
            self.logger.warning('Error: %s',response[1])
        else: 
            QMessageBox.warning(self, 'remoteXL: Error', "Background service send unknown signal! Restart service and try again.", QMessageBox.Ok)
            self.logger.warning("Error: Background service send unknown signal! Restart service and try again.")

class NewConnection_Window(QMainWindow):
    def __init__(self,parent):
        super().__init__(parent) 
        self.logger = logging.getLogger(__name__)
        self.parent = parent
        self.settings = parent.config_data['known_settings'] 
        self.remoteXLApp = parent.remoteXLApp
        self.ui = Ui_NewConnection_Window()
        self.ui.setupUi(self)
        self.setWindowTitle("remoteXL")           
        self.ui.host_comboBox.addItem('')
        self.ui.username_comboBox.addItem('')
        for setting in self.settings:
            if setting['remote']:         
                self.ui.host_comboBox.addItem(setting['host'])
                self.ui.username_comboBox.addItem(setting['user'])
        self.show()
        
        self.ui.connect_pushButton.clicked.connect(self.connect)

    def connect(self):
            
        connection = {'user':self.ui.username_comboBox.currentText().strip(),'host':self.ui.host_comboBox.currentText().strip()}
        response = self.remoteXLApp.call_backend(['new_connection',connection])
        
        if response[0] == 'auth_start':
            self.remoteXLApp.timeout = 30    
            success = self.remoteXLApp.authentication(connection, self)
            self.remoteXLApp.timeout = 5  
            if success:
                self.close() 
                self.parent.refresh_pressed()
        elif response[0] == 'error':
            QMessageBox.warning(self, 'remoteXL: Error', response[1], QMessageBox.Ok)
            self.logger.warning('Error: %s',response[1])
        else: 
            QMessageBox.warning(self, 'remoteXL: Error', "Background service send unknown signal! Restart service and try again.", QMessageBox.Ok)
            self.logger.warning("Error: Background service send unknown signal! Restart service and try again.")
            


class ConnectionWidget(QWidget):
    def __init__(self,connection:dict):
        super().__init__()
        self.connection = connection
        
        self.layout = QGridLayout(self)
        self.layout.setObjectName("Layout")
        bold_font = QFont()
        bold_font.setPointSize(8)
        bold_font.setBold(True)
        
        self.connection_label = QLabel() 
        self.connection_label.setFont(bold_font)
        self.connection_label.setText('{}@{}'.format(self.connection['user'],self.connection['host']))
        self.layout.addWidget(self.connection_label)
        self.adjustSize()
 
class JobWidget(QWidget):
    def __init__(self,job:dict):
        super().__init__()
        self.job = job
        self.setting = job['setting']
        
        self.gridLayout = QGridLayout(self)
        self.gridLayout.setObjectName("gridLayout")  

        font = QFont()
        font.setPointSize(8)
        font.setBold(False)
        bold_font = QFont()
        bold_font.setPointSize(8)
        bold_font.setBold(True)
              
        
        
        self.file_label = QLabel() 
        self.file_label.setFont(bold_font)
        self.file_label.setText(self.job['local_file'])
        self.gridLayout.addWidget(self.file_label, 0, 0, 1, 3)
        
        self.job_state_label = QLabel() 
        self.job_state_label.setFont(font)
        self.job_state_label.setText('Status: {}'.format(self.job['status']))
        self.gridLayout.addWidget(self.job_state_label, 1, 0, 1, 1)
        
        self.start_time_label = QLabel() 
        self.start_time_label.setFont(font)
        self.start_time_label.setText('Start time: {}'.format(datetime.fromtimestamp(self.job['start_time']).strftime("%H:%M:%S (%d-%B-%Y)")))
        self.gridLayout.addWidget(self.start_time_label, 1, 1, 1, 2)
        
        self.user_host_label = QLabel()
        self.user_host_label.setFont(font)   
        user_host_string = '{}@{}'.format( self.setting['user'],  self.setting['host'])
        self.user_host_label.setText(user_host_string)   
        self.gridLayout.addWidget(self.user_host_label, 2, 0, 1, 1)
             
        self.queuingsystem_label = QLabel()
        self.queuingsystem_label.setFont(font)
        if 'queingsystem' in  self.setting:
            queuingsystem_string = 'Queuingsystem: {}'.format( self.setting['queingsystem']['displayname'])
        else:
            queuingsystem_string = ''
        self.queuingsystem_label.setText(queuingsystem_string)  
        self.gridLayout.addWidget(self.queuingsystem_label, 2, 1, 1, 2)
        
        for key,value in  self.setting['queingsystem'].items():
            
            if key == 'name' or key == 'displayname':
                continue
            label = QLabel()
            label.setFont(font)
            label.setText('{}: {}'.format(key,value))
            self.gridLayout.addWidget(label)

        self.adjustSize()