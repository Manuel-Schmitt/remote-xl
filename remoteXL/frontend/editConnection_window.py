from remoteXL.frontend.newConnection_window import NewConnection_Window
from PyQt5.QtWidgets import QMessageBox

class EditConnection_Window(NewConnection_Window):
    
    def __init__(self,con,remoteXLApp,parent=None,wait_loop=None):
        super().__init__(remoteXLApp,parent,wait_loop)
        self.connection = con
        self.ui.title_label.setText('Edit Connection:' )
        if self.remote_settings != self.connection['remote']:
            self.change_remote_local() 
        self.delete_pushButton = self.ui.local_remote_pushButton
        self.delete_pushButton.setText('Delete')
        self.delete_pushButton.disconnect()
        self.delete_pushButton.clicked.connect(self.delete_clicked)
        self._set_fields()
        
    def _set_fields(self):
        if self.remote_settings:
            self.ui.username_comboBox.setCurrentText(self.connection['user']) 
            self.ui.host_comboBox.setCurrentText(self.connection['host']) 
            self.ui.shelxlpath_comboBox.setCurrentText(self.connection['shelxlpath']) 
            for index in range(self.ui.queuingsystem_comboBox.count()):
                if self.ui.queuingsystem_comboBox.itemData(index)['Name'] == self.connection['queingsystem']['name']:
                    self.ui.queuingsystem_comboBox.setCurrentIndex(index)

            for setting in self.queue_data:
            
                if setting['Type'] == 'LineEdit':
                    setting['QObject'].setText(self.connection['queingsystem'][setting['Name']])                 
                elif setting['Type'] == 'SpinBox':
                    setting['QObject'].setValue(self.connection['queingsystem'][setting['Name']])   
                elif setting['Type'] == 'ComboBox':
                    index = setting['QObject'].findText(self.connection['queingsystem'][setting['Name']])
                    setting['QObject'].setCurrentIndex(index)                                                 
                elif setting['Type'] == 'WalltimeWidget':
                    setting['QObject'].set_walltime(self.connection['queingsystem'][setting['Name']])
                    
        else:
            self.ui.local_shelxlpath_lineEdit.setText(self.connection['path']) 
    
    def delete_clicked(self):
        yes_no = QMessageBox.question(self,'remoteXL', "Do you really want to delete this connection?", QMessageBox.Yes | QMessageBox.No)        
        if yes_no == QMessageBox.Yes:
            self.remoteXLApp.backend_connection.send(['delete_connection',self.connection])
            self.close()
                
    def save_clicked(self):
        self.connection.update(self._get_data())
        response = self.remoteXLApp.call_backend(['edit_connection',self.connection])
        if response[0] == 'error':
            QMessageBox.warning(self, 'remoteXL: Error', response[1], QMessageBox.Ok)
        else:
            self.close()