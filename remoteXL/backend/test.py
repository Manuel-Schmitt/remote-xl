import sys
#import remoteXL.backend.queingsystems
from remoteXL.backend.queingsystems.base_queingsystem import Base_Quingsystem


print(sys.modules)



#print(Base_Quingsystem.needed_settings())
print(Base_Quingsystem.get_subclass_by_name('Sun_Grid_Engine'))
print(Base_Quingsystem.get_all_settings())