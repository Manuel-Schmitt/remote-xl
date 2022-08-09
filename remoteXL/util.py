from threading import Timer


class RepeatTimer(Timer):
    def __init__(self,interval, function,start_delay=0):
        super().__init__(interval, function)
        self.start_delay = start_delay
        self.daemon = True
        
    def run(self):
        self.finished.wait(self.start_delay)
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs) 
    
