from remoteXL.frontend.newSetting_window import NewSetting_Window
from PyQt5.QtWidgets import QMessageBox

class EditSetting_Window(NewSetting_Window):
    
    def __init__(self,setting,remoteXLApp,parent=None,wait_loop=None):
        super().__init__(remoteXLApp,parent,wait_loop)
        self.setting = setting
        self.ui.title_label.setText('Edit:' )
        if self.remote_settings != self.setting['remote']:
            self.change_remote_local() 
        self.delete_pushButton = self.ui.local_remote_pushButton
        self.delete_pushButton.setText('Delete')
        self.delete_pushButton.disconnect()
        self.delete_pushButton.clicked.connect(self.delete_clicked)
        self._set_fields()
        
    def _set_fields(self):
        if self.remote_settings:
            self.ui.username_comboBox.setCurrentText(self.setting['user']) 
            self.ui.host_comboBox.setCurrentText(self.setting['host']) 
            self.ui.shelxlpath_comboBox.setCurrentText(self.setting['shelxlpath']) 
            for index in range(self.ui.queuingsystem_comboBox.count()):
                if self.ui.queuingsystem_comboBox.itemData(index)['Name'] == self.setting['queingsystem']['name']:
                    self.ui.queuingsystem_comboBox.setCurrentIndex(index)

            for setting in self.queue_data:
            
                if setting['Type'] == 'LineEdit':
                    setting['QObject'].setText(self.setting['queingsystem'][setting['Name']])                 
                elif setting['Type'] == 'SpinBox':
                    setting['QObject'].setValue(self.setting['queingsystem'][setting['Name']])   
                elif setting['Type'] == 'ComboBox':
                    index = setting['QObject'].findText(self.setting['queingsystem'][setting['Name']])
                    setting['QObject'].setCurrentIndex(index)                                                 
                elif setting['Type'] == 'WalltimeWidget':
                    setting['QObject'].set_walltime(self.setting['queingsystem'][setting['Name']])
                    
        else:
            self.ui.local_shelxlpath_lineEdit.setText(self.setting['path']) 
    
    def delete_clicked(self):
        yes_no = QMessageBox.question(self,'remoteXL', "Do you really want to delete this setting?", QMessageBox.Yes | QMessageBox.No)        
        if yes_no == QMessageBox.Yes:
            self.remoteXLApp._send(['delete_setting',self.setting])
            self.close()
                
    def save_clicked(self):
        self.setting.update(self._get_data())
        response = self.remoteXLApp.call_backend(['edit_setting',self.setting])
        if response[0] == 'error':
            QMessageBox.warning(self, 'remoteXL: Error', response[1], QMessageBox.Ok)
        else:
            self.close()