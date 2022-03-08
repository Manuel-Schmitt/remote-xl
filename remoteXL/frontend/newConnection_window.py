import sys
import socket
import json
import logging
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton,QMessageBox, QWidget, QLabel, QLineEdit, QComboBox, QSpinBox,QHBoxLayout,QFormLayout,QSizePolicy, QFileDialog
from PyQt5.QtGui import  QFont
from PyQt5.QtCore import QSize,Qt,QEventLoop


from remoteXL.gui.Ui_NewConnection_Window import Ui_NewConnection_Window
from remoteXL import main


class NewConnection_Window(QMainWindow):
    
    def __init__(self,remoteXLApp,parent=None,wait_loop=None):
        super().__init__(parent)    
        self.remoteXLApp = remoteXLApp
        if parent is not None:
            self.setWindowModality(Qt.WindowModality.WindowModal)
        self.wait_loop = wait_loop
        self.logger = logging.getLogger(__name__)
        self.ui = Ui_NewConnection_Window()
        self.ui.setupUi(self)
        self.setWindowTitle("remoteXL")    
        
        self.remote_settings = True
        self.ui.local_widget.setVisible(False)
        self.ui.local_remote_pushButton.clicked.connect(self.change_remote_local)
        self.ui.save_pushButton.clicked.connect(self.save_clicked)
        self.ui.browse_pushButton.clicked.connect(self.browse_for_shelxlPath)

        self.queing_systems = self.remoteXLApp.call_backend(['queingsystems'])       
        for system in  self.queing_systems:
            self.ui.queuingsystem_comboBox.addItem(system['Displayname'], system)  
        self.ui.queuingsystem_comboBox.currentIndexChanged.connect(self.create_queue_widget)   
              
        self.create_queue_widget()
        self.add_known_connections_to_comboBoxes()
        self.show()
        
    def add_known_connections_to_comboBoxes(self):
        #TODO Finisch
        self.ui.host_comboBox.addItem('')
        self.ui.username_comboBox.addItem('')
        self.ui.shelxlpath_comboBox.addItem('')
        known_connections = self.remoteXLApp.call_backend(['known_connections'])
        for idx,con in enumerate(known_connections):    
            if con['remote']:         
                self.ui.host_comboBox.addItem(con['host'])
                self.ui.username_comboBox.addItem(con['user'])
                self.ui.shelxlpath_comboBox.addItem(con['shelxlpath'])

        
    def browse_for_shelxlPath(self):
        path = QFileDialog.getOpenFileName(self,'ShelXL Path',r'\ ' )[0]
        self.ui.local_shelxlpath_lineEdit.setText(path)
        
    def save_clicked(self):
        response = self.remoteXLApp.call_backend(['new_connection',self._get_data()])
        if response[0] == 'error':
            QMessageBox.warning(self, 'remoteXL: Error', response[1], QMessageBox.Ok)
        else:
            self.close()
        
        
    def get_data_on_close(self):
        if self.wait_loop is None:           
            self.wait_loop = QEventLoop()
        self.wait_loop.exec_()
        return _get_data()
    
    def wait_for_close(self):
        if self.wait_loop is None:           
            self.wait_loop = QEventLoop()
        self.wait_loop.exec_()
        return 
    
    def _get_data(self):
        connection_data = {'remote':self.remote_settings}
        if self.remote_settings:
            connection_data.update({'user':str(self.ui.username_comboBox.currentText().strip())})
            connection_data.update({'host':str(self.ui.host_comboBox.currentText().strip())})
            connection_data.update({'shelxlpath':str(self.ui.shelxlpath_comboBox.currentText().strip())})
            connection_data.update({'queingsystem':{'name':str(self.ui.queuingsystem_comboBox.currentData()['Name'])}})
            connection_data['queingsystem'].update({'displayname':str(self.ui.queuingsystem_comboBox.currentData()['Displayname'])})
            for setting in self.queue_data:
            
                if setting['Type'] == 'LineEdit':
                    connection_data['queingsystem'].update({setting['Name'] :str(setting['QObject'].text().strip())})                    
                elif setting['Type'] == 'SpinBox':
                    connection_data['queingsystem'].update({setting['Name'] :setting['QObject'].value()})    
                elif setting['Type'] == 'ComboBox':
                    connection_data['queingsystem'].update({setting['Name'] :str(setting['QObject'].currentText().strip())})  
                elif setting['Type'] == 'WalltimeWidget':
                    connection_data['queingsystem'].update({setting['Name'] :setting['QObject'].get_walltime()}) 
        else:
            connection_data.update({'path':str(self.ui.local_shelxlpath_lineEdit.text().strip())})    
        return connection_data
    
    def closeEvent(self,event):
        if self.wait_loop is not None:
            self.wait_loop.quit()
        event.accept()
        
        
    def change_remote_local(self):   
         
        self.remote_settings = not self.remote_settings

           
        if self.remote_settings:
            self.ui.host_widget.setVisible(True)
            self.ui.host_line.setVisible(True)
            self.ui.queingsystem_widget.setVisible(True)
            self.ui.queue_widget.setVisible(True)
            self.ui.local_widget.setVisible(False)
            self.ui.local_remote_pushButton.setText('Local')
        else:
            self.ui.host_widget.setVisible(False)
            self.ui.host_line.setVisible(False)
            self.ui.queingsystem_widget.setVisible(False)
            self.ui.queue_widget.setVisible(False)
            self.ui.local_widget.setVisible(True)
            self.ui.local_remote_pushButton.setText('Remote')
        self.ui.main_widget.adjustSize()
        self.adjustSize()
        
        
    def create_queue_widget(self):
        settings = self.ui.queuingsystem_comboBox.currentData()['Settings']
        
        
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        font.setWeight(75)
        queue_layout = self.ui.queue_widget.layout()

        #Delete entries in widget
        for i in reversed(range(queue_layout.count())): 
            queue_layout.itemAt(i).widget().deleteLater()
            queue_layout.itemAt(i).widget().setParent(None)
            
        self.queue_data = []
        
        for idx, setting in enumerate(settings):

            label = QLabel(self.ui.queue_widget)
            label.setFont(font)
            label.setIndent(12)
            label.setObjectName('{}_label'.format(setting['Label']))
            label.setText('{}:'.format(setting['Label']))
            queue_layout.setWidget(idx, QFormLayout.LabelRole, label)      
            
            if setting['Type'] == 'LineEdit':
                qobj = QLineEdit(self.ui.queue_widget)
                qobj.setObjectName('{}_{}'.format(setting['Label'],setting['Type']))
                if 'Default' in setting:
                    qobj.setText(setting['Default'])
                queue_layout.setWidget(idx, QFormLayout.FieldRole, qobj)
                setting['QObject'] = qobj
                self.queue_data.append(setting)
            elif setting['Type'] == 'SpinBox':
                qobj = QSpinBox(self.ui.queue_widget)
                qobj.setObjectName('{}_{}'.format(setting['Label'],setting['Type']))
                if 'Min' in setting:                   
                    qobj.setMinimum(int(setting['Min']))
                if 'Max' in setting:
                    qobj.setMaximum(int(setting['Max']))
                if 'Default' in setting:
                    qobj.setValue(int(setting['Default']))
                queue_layout.setWidget(idx, QFormLayout.FieldRole, qobj)
                setting['QObject'] = qobj
                self.queue_data.append(setting)
            elif setting['Type'] == 'ComboBox':
                qobj = QComboBox(self.ui.queue_widget)
                qobj.setObjectName('{}_{}'.format(setting['Label'],setting['Type']))                 
                if 'Values' in setting:
                    qobj.addItems(setting['Values'])
                if 'Default' in setting:
                    index = qobj.findText(setting['Default'], Qt.MatchFixedString)
                    if index >= 0:
                        qobj.setCurrentIndex(index)
                queue_layout.setWidget(idx, QFormLayout.FieldRole, qobj)   
                setting['QObject'] = qobj
                self.queue_data.append(setting)        
            elif setting['Type'] == 'WalltimeWidget':
                qobj = Walltime_Widget(setting['Label'],self.ui.queue_widget)
                if 'MaxDays' in setting:
                    qobj.walltime_days_spinBox.setMaximum(int(setting['MaxDays']))
                queue_layout.setWidget(idx, QFormLayout.FieldRole, qobj)     
                setting['QObject'] = qobj
                self.queue_data.append(setting)      
            
            
            
    
        
class Walltime_Widget(QWidget):
    def __init__ (self,label:str,parent=None):
        super().__init__(parent)
        self.setObjectName('{}_Widget'.format(label))

        self.horizontalLayout = QHBoxLayout(self)
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout.setObjectName("{}_horizontalLayout".format(label))
        
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        
        self.walltime_days_spinBox = QSpinBox(self)
        self.walltime_days_spinBox.setSizePolicy(sizePolicy)
        self.walltime_days_spinBox.setMinimumSize(QSize(50, 0))
        self.walltime_days_spinBox.setAlignment(Qt.AlignRight|Qt.AlignTrailing|Qt.AlignVCenter)
        self.walltime_days_spinBox.setObjectName("{}_days_spinBox".format(label))
        self.horizontalLayout.addWidget(self.walltime_days_spinBox)
        
        self.walltime_days_label = QLabel(self)
        self.walltime_days_label.setObjectName("{}_days_label".format(label))
        self.walltime_days_label.setText('days')
        self.horizontalLayout.addWidget(self.walltime_days_label)
        
        self.walltime_hours_spinBox = QSpinBox(self)
        self.walltime_hours_spinBox.setSizePolicy(sizePolicy)
        self.walltime_hours_spinBox.setMinimumSize(QSize(50, 0))
        self.walltime_hours_spinBox.setAlignment(Qt.AlignRight|Qt.AlignTrailing|Qt.AlignVCenter)
        self.walltime_hours_spinBox.setObjectName("{}_hours_spinBox".format(label))
        self.horizontalLayout.addWidget(self.walltime_hours_spinBox)
        
        self.walltime_hours_label = QLabel(self)
        self.walltime_hours_label.setObjectName("{}_hours_label".format(label))
        self.walltime_hours_label.setText('hours')
        self.horizontalLayout.addWidget(self.walltime_hours_label)
        
        self.walltime_minutes_spinBox = QSpinBox(self)
        self.walltime_minutes_spinBox.setSizePolicy(sizePolicy)
        self.walltime_minutes_spinBox.setMinimumSize(QSize(50, 0))
        self.walltime_minutes_spinBox.setAlignment(Qt.AlignRight|Qt.AlignTrailing|Qt.AlignVCenter)
        self.walltime_minutes_spinBox.setMaximum(59)
        self.walltime_minutes_spinBox.setObjectName("{}_minutes_spinBox".format(label))
        self.horizontalLayout.addWidget(self.walltime_minutes_spinBox)
        
        self.walltime_minutes_label = QLabel(self)
        self.walltime_minutes_label.setObjectName("{}_minutes_label".format(label))
        self.walltime_minutes_label.setText('minutes')
        self.horizontalLayout.addWidget(self.walltime_minutes_label)
        
    def get_walltime(self):
        return '{}-{}:{}'.format(self.walltime_days_spinBox.value(),self.walltime_hours_spinBox.value(),self.walltime_minutes_spinBox.value())
       
    def set_walltime(self,walltimeString):
        days = walltimeString.split('-')[0]
        hours = walltimeString.split('-')[1].split(':')[0]
        minutes = walltimeString.split('-')[1].split(':')[1]
        
        self.walltime_days_spinBox.setValue(int(days))
        self.walltime_hours_spinBox.setValue(int(hours))
        self.walltime_minutes_spinBox.setValue(int(minutes))