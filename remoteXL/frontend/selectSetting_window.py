import logging

from PyQt5.QtWidgets import QMainWindow, QPushButton,QWidget, QLabel,QHBoxLayout,QGridLayout, QVBoxLayout,QDialog
from PyQt5.QtGui import  QFont
from PyQt5.QtCore import QSize
from PyQt5 import Qt
from remoteXL.gui.Ui_SelectSetting_Window import Ui_SelectSetting_Window
from remoteXL.frontend.newSetting_window import NewSetting_Window
from remoteXL.frontend.editSetting_window import EditSetting_Window



class SelectSetting_Window(QMainWindow):
    def __init__(self,remoteXLApp,parent=None):
        super().__init__(parent)    
        self.remoteXLApp = remoteXLApp
        self.logger = logging.getLogger(__name__)
        self.ui = Ui_SelectSetting_Window()
        self.ui.setupUi(self)
        self.setWindowTitle("remoteXL")    
        self.ui.setting_tableWidget.verticalHeader().setSectionResizeMode(Qt.QHeaderView.Fixed)
        self.ui.setting_tableWidget.verticalHeader().setSectionsMovable(True)
        self.ui.setting_tableWidget.verticalHeader().sectionMoved.connect(self.section_moved)
        self.set_setting_table()       
        
        self.ui.new_pushButton.clicked.connect(self.new_pressed)
        self.ui.edit_pushButton.clicked.connect(self.edit_pressed)
        self.ui.run_pushButton.clicked.connect(self.run_pressed)
        self.ui.setting_tableWidget.cellDoubleClicked.connect(self.run_pressed)
        self.show()
        
    def section_moved(self,logical_position,old_position,new_position):   
        self.remoteXLApp._send(['change_order',(old_position,new_position)])
        self.set_setting_table() 
        

    def run_pressed(self,*args):
        
        row = self.ui.setting_tableWidget.currentRow()    
        if row != -1: 
            selected_setting = self.ui.setting_tableWidget.cellWidget(row, 0).setting
            
            if self.ui.default_radioButton.isChecked():
                self.remoteXLApp._send(['set_file_default',selected_setting])
            self.remoteXLApp.runXL(selected_setting,self)
        
        
    def new_pressed(self):
        
        ncw = NewSetting_Window(remoteXLApp=self.remoteXLApp,parent=self)    
        ncw.wait_for_close()
        self.set_setting_table()   
        
    def edit_pressed(self):
        
        row = self.ui.setting_tableWidget.currentRow()
        
        if row != -1: 
            selected_setting = self.ui.setting_tableWidget.cellWidget(row, 0).setting
            ecw = EditSetting_Window(selected_setting,remoteXLApp=self.remoteXLApp,parent=self)    
            ecw.wait_for_close()
            self.set_setting_table()      
        
      
    def set_setting_table(self): 
        self.ui.setting_tableWidget.setRowCount(0)
        settings = self.remoteXLApp.call_backend(['known_settings'])
        self.ui.setting_tableWidget.setRowCount(len(settings))   
        
        for idx,setting in enumerate(settings):            
            cw = CellWidget(setting)
            self.ui.setting_tableWidget.setCellWidget(idx,0,cw)
            self.ui.setting_tableWidget.setRowHeight(idx, cw.height() )
            

        
    
        
 
class CellWidget(QWidget):
    def __init__(self,setting:dict):
        self.setting = setting
        super().__init__()
        self.gridLayout = QGridLayout(self)
        self.gridLayout.setObjectName("gridLayout")  

        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
              
        self.user_host_label = QLabel()
        self.user_host_label.setFont(font)
        if self.setting['remote']:
            user_host_string = '{}@{}'.format( self.setting['user'],  self.setting['host'])
            self.user_host_label.setText(user_host_string)   
            self.gridLayout.addWidget(self.user_host_label, 0, 0, 1, 1)
        else:
            user_host_string = 'local' 
            self.user_host_label.setText(user_host_string)   
            self.gridLayout.addWidget(self.user_host_label, 0, 0, 1, 1)   
            font = QFont()
            font.setPointSize(8)
            font.setBold(False)   
            self.path_label = QLabel()
            self.path_label.setFont(font)
            self.path_label.setText(self.setting['path'])
            self.gridLayout.addWidget(self.path_label)
            self.adjustSize()
            return

        
        font = QFont()
        font.setPointSize(8)
        font.setBold(False)
       
        
        self.queuingsystem_label = QLabel()
        self.queuingsystem_label.setFont(font)
        if 'queingsystem' in  self.setting:
            queuingsystem_string = 'Queuingsystem: {}'.format( self.setting['queingsystem']['displayname'])
        else:
            queuingsystem_string = ''
        self.queuingsystem_label.setText(queuingsystem_string)  
        self.gridLayout.addWidget(self.queuingsystem_label, 0, 1, 1, 2)
        
        for key,value in  self.setting['queingsystem'].items():
            
            if key == 'name' or key == 'displayname':
                continue
            label = QLabel()
            label.setFont(font)
            label.setText('{}: {}'.format(key,value))
            self.gridLayout.addWidget(label)

        self.adjustSize()
        
class RunningJobDialog(QDialog):
    def __init__(self,setting:dict,start_time,ins_changed,continue_function,stop_function):
        super().__init__()
        
        self.setWindowTitle('remoteXL')
        
        layout = QVBoxLayout()
        layout.addWidget(QLabel('Refinement was started at {} with:'.format(start_time)))
        layout.addWidget(CellWidget(setting))
             
        button_widget = QWidget()
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(2,2,2,2)
        
        self.continue_button = QPushButton('Continue')
        self.continue_button.setMaximumSize(QSize(100, 1000))       
        self.continue_button.clicked.connect(lambda: continue_function(setting, self))
        
        self.keep_job_button = QPushButton('Continue refinement')
        self.keep_job_button.setMaximumSize(QSize(150, 1000))
        self.keep_job_button.clicked.connect(lambda: continue_function(setting, self))
        
        self.keep_changes_button = QPushButton('Keep changes')
        self.keep_changes_button.setMaximumSize(QSize(100, 1000))
        self.keep_changes_button.clicked.connect(stop_function)
        
        if ins_changed:
            layout.addWidget(QLabel('ATTENTION: The ins file was modified after the refinement was started!'))
            layout.addWidget(QLabel('How do you want to proceed?'))
            button_layout.addWidget(self.keep_changes_button)
            button_layout.addWidget(self.keep_job_button)
        else:        
            button_layout.addWidget(self.continue_button)
        
        button_widget.setLayout(button_layout)
        layout.addWidget(button_widget)
        
        self.setLayout(layout)
        self.show()