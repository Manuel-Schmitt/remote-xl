import logging

from PyQt5.QtWidgets import QMessageBox

from remoteXL.frontend.selectSetting_window import SelectSetting_Window,CellWidget
from remoteXL.frontend.newSetting_window import NewSetting_Window
from remoteXL.frontend.editSetting_window import EditSetting_Window



class SelectDefault_Window(SelectSetting_Window):
    def __init__(self,remoteXLApp,globel_defaults=True,parent=None):  
        self.remoteXLApp = remoteXLApp
        self.global_defaults = globel_defaults
        if self.remoteXLApp.ins_hkl_path is None and not self.global_defaults:
            self.global_defaults = True           
        self.known_settings = None
        self.default_id = None
        self.logger = logging.getLogger(__name__)   
        
        super().__init__(remoteXLApp,parent)  
              
        if self.global_defaults:
            self.ui.title_label.setText('Select global default:')
        else:
            self.ui.title_label.setText('Select file default:')
        
        self.ui.default_label.hide()
        self.ui.default_radioButton.hide()
        self.ui.run_pushButton.setText('Select')
        self.ui.cancel_pushButton.setText('No default')
        self.ui.cancel_pushButton.clicked.disconnect(self.close)
        self.ui.cancel_pushButton.clicked.connect(lambda: self.select_pressed(True))
        self.ui.run_pushButton.clicked.disconnect(self.run_pressed)
        self.ui.run_pushButton.clicked.connect(self.select_pressed)
        self.ui.setting_tableWidget.cellDoubleClicked.disconnect(self.run_pressed)
        self.ui.setting_tableWidget.cellDoubleClicked.connect(lambda: self.select_pressed(False))
        
        
        self.show()
               
        
        
    def select_pressed(self,no_defaults=False):
        if no_defaults:
            setting = {'id':''}
        else:
            setting = self.get_selected_setting()
        if setting is None:
            return 
        
        if self.global_defaults:
            response = self.remoteXLApp.call_backend(['set_global_defaults',setting])
        else:
            response = self.remoteXLApp.call_backend(['set_file_defaults',setting,str(self.remoteXLApp.ins_hkl_path)])
                
        if response[0] == 'ok': 
            self.close()
        elif response[0] == 'error': 
            QMessageBox.warning(self, 'remoteXL: Error', response[1], QMessageBox.Ok)
            self.logger.warning('Error: %s',response[1])
    
            
        
    def set_setting_table(self): 
        self.ui.setting_tableWidget.setRowCount(0)
        self.known_settings = self.remoteXLApp.call_backend(['known_settings'])
        
        if self.global_defaults:
            self.default_id = self.remoteXLApp.call_backend(['get_global_defaults'])
        else:
            self.default_id = self.remoteXLApp.call_backend(['get_file_defaults',str(self.remoteXLApp.ins_hkl_path)])
            
        
        self.ui.setting_tableWidget.setRowCount(len(self.known_settings))   
        
        for idx,setting in enumerate(self.known_settings):            
            cw = CellWidget(setting)
            self.ui.setting_tableWidget.setCellWidget(idx,0,cw)
            self.ui.setting_tableWidget.setRowHeight(idx, cw.height())
            if setting['id'] == self.default_id:
                cw.setStyleSheet('background-color: rgb(145, 255, 145)')
                cw.setAutoFillBackground(True)
            
    def new_pressed(self):     
        ncw = NewSetting_Window(remoteXLApp=self.remoteXLApp,parent=self,show_run_button=False)    
        ncw.wait_for_close()
        self.set_setting_table()   
        
    def edit_pressed(self):
        
        selected_setting =  self.get_selected_setting()
        if selected_setting is not None: 
            ecw = EditSetting_Window(selected_setting,remoteXLApp=self.remoteXLApp,parent=self,show_run_button=False)    
            ecw.wait_for_close()
            self.set_setting_table()             
            
            