from abc import ABC, abstractstaticmethod

class Base_Quingsystem(ABC):
    
    @classmethod
    def name(self):
        return self.__name__
    
    @classmethod
    def displayname(cls):
        try:
            if cls._displayname is None:
                return cls.__name__
            else:
                return cls._displayname
        except AttributeError:
            return cls.__name__

    @abstractstaticmethod
    def needed_settings():
        raise NotImplementedError
    
        settings = []
        settings.append({
            'Name' : 'queue',
            'Label':'Queue',
            'Type' : 'LineEdit',
            'Default': 'StartText'
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
         
        settings.append({
            'Name' : 'selection',
            'Label':'Select',
            'Type' : 'ComboBox',
            'Values' : ['1','2','3'],
            'Default' : '2'
        })
        
        return settings
    
    @classmethod
    def check_settings(cls,settings:dict):       
        #return None if ok or error message as string
        if settings['user'] == '':
             return 'Error: Username was not given'
        if settings['host'] == '':
             return 'Error: Host was not given'
        if settings['shelxlpath'] == '':
             return 'Error: Path to ShelXL was not given'      
        for needed in cls.needed_settings():
            if not needed['Name'] in settings['queingsystem']:
                return 'Error: {} was not given'.format(needed['Lable'])
        return None    
    
    @classmethod                    
    def all_subclasses(cls):
            return set(cls.__subclasses__()).union([s for c in cls.__subclasses__() for s in c.all_subclasses()])
        
    @classmethod
    def get_subclass_by_name(cls,name):       
        for subclass in cls.all_subclasses():
            if subclass.name() == name:
                return subclass
    
    @staticmethod
    def get_all_settings():   
        all = []
        for subclass in Base_Quingsystem.all_subclasses():
            all.append( {'Name':subclass.name(),'Displayname': subclass.displayname(), 'Settings':subclass.needed_settings()} )
        return all    