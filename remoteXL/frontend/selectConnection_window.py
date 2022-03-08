import sys
import socket
import json
import logging

from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QWidget, QLabel, QLineEdit, QComboBox, QSpinBox,QHBoxLayout,QFormLayout,QSizePolicy, QTableWidgetItem,QGridLayout
from PyQt5.QtGui import  QFont
from PyQt5.QtCore import QSize, QEventLoop
from PyQt5 import Qt
from remoteXL.gui.Ui_SelectConnection_Window import Ui_SelectConnection_Window
from remoteXL.frontend.newConnection_window import NewConnection_Window
from remoteXL.frontend.editConnection_window import EditConnection_Window
from remoteXL import main


class SelectConnection_Window(QMainWindow):
    def __init__(self,remoteXLApp,parent=None):
        super().__init__(parent)    
        self.remoteXLApp = remoteXLApp
        self.logger = logging.getLogger(__name__)
        self.ui = Ui_SelectConnection_Window()
        self.ui.setupUi(self)
        self.setWindowTitle("remoteXL")    
        self.ui.connection_tableWidget.verticalHeader().setSectionResizeMode(Qt.QHeaderView.Fixed)
        self.ui.connection_tableWidget.verticalHeader().setSectionsMovable(True)
        self.ui.connection_tableWidget.verticalHeader().sectionMoved.connect(self.section_moved)
        self.set_connection_table()       
        
        self.ui.new_pushButton.clicked.connect(self.new_pressed)
        self.ui.edit_pushButton.clicked.connect(self.edit_pressed)
        self.ui.run_pushButton.clicked.connect(self.run_pressed)
        self.show()
        
    def section_moved(self,logical_position,old_position,new_position):   
        self.remoteXLApp.backend_connection.send(['change_order',(old_position,new_position)])
        self.set_connection_table() 
        

    def run_pressed(self):
        
        row = self.ui.connection_tableWidget.currentRow()    
        if row != -1: 
            selected_connection = self.ui.connection_tableWidget.cellWidget(row, 0).connection
            self.close()
            self.remoteXLApp.runXL(selected_connection)
        
        
    def new_pressed(self):
        
        ncw = NewConnection_Window(remoteXLApp=self.remoteXLApp,parent=self)    
        ncw.wait_for_close()
        self.set_connection_table()   
        
    def edit_pressed(self):
        
        row = self.ui.connection_tableWidget.currentRow()
        
        if row != -1: 
            selected_connection = self.ui.connection_tableWidget.cellWidget(row, 0).connection
            ecw = EditConnection_Window(selected_connection,remoteXLApp=self.remoteXLApp,parent=self)    
            ecw.wait_for_close()
            self.set_connection_table()      
        
      
    def set_connection_table(self): 
        self.ui.connection_tableWidget.setRowCount(0)
        connections = self.remoteXLApp.call_backend(['known_connections'])
        self.ui.connection_tableWidget.setRowCount(len(connections))   
        
        for idx,connection in enumerate(connections):            
            cw = CellWidget(connection)
            self.ui.connection_tableWidget.setCellWidget(idx,0,cw)
            self.ui.connection_tableWidget.setRowHeight(idx, cw.height() )
            

        
    
        
 
class CellWidget(QWidget):
     def __init__(self,connection:dict):
        self.connection = connection
        super().__init__()
        self.gridLayout = QGridLayout(self)
        self.gridLayout.setObjectName("gridLayout")  

        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
              
        self.user_host_label = QLabel()
        self.user_host_label.setFont(font)
        if self.connection['remote']:
            user_host_string = '{}@{}'.format( self.connection['user'],  self.connection['host'])
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
            self.path_label.setText(self.connection['path'])
            self.gridLayout.addWidget(self.path_label)
            self.adjustSize()
            return

        
        font = QFont()
        font.setPointSize(8)
        font.setBold(False)
       
        
        self.queuingsystem_label = QLabel()
        self.queuingsystem_label.setFont(font)
        if 'queingsystem' in  self.connection:
            queuingsystem_string = 'Queuingsystem: {}'.format( self.connection['queingsystem']['displayname'])
        else:
            queuingsystem_string = ''
        self.queuingsystem_label.setText(queuingsystem_string)  
        self.gridLayout.addWidget(self.queuingsystem_label, 0, 1, 1, 2)
        
        for key,value in  self.connection['queingsystem'].items():
            
            if key == 'name' or key == 'displayname':
                continue
            label = QLabel()
            label.setFont(font)
            label.setText('{}: {}'.format(key,value))
            self.gridLayout.addWidget(label)

        self.adjustSize()