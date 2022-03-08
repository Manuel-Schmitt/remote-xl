from remoteXL.backend.queingsystems.base_queingsystem import Base_Quingsystem

class Sun_Grid_Engine(Base_Quingsystem):
    _displayname = 'Sun Grid Engine'
    
    @staticmethod
    def needed_settings():
        settings = []
        settings.append({
            'Name' : 'queue',
            'Label':'Queue',
            'Type' : 'LineEdit'
        })
         
        settings.append({
            'Name' : 'cpu',
            'Label':'CPU',
            'Type' : 'SpinBox',
            'Min' : '1',
            'Max' : '99',
            'Default' : '1',
        })
        settings.append({
            'Name' : 'walltime',
            'Label':'Walltime',
            'Type' : 'WalltimeWidget',
            'MaxDays' : '14',
        })              
        return settings
    
class testclass(Base_Quingsystem):
    _displayname = 'TTTTEST'
    
    @staticmethod
    def needed_settings():
        settings = []
        settings.append({
            'Name' : 'Test',
            'Label':'Test',
            'Type' : 'LineEdit'
        })
         
                    
        return settings
