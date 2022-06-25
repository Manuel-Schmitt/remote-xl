from remoteXL.backend.queingsystems.base_queingsystem import BaseQuingsystem

class Sun_Grid_Engine(BaseQuingsystem):
    _displayname = 'Sun Grid Engine'
    @classmethod
    def job_script_path(cls,job):
        return job.ins_hkl_path.with_suffix('.qsub')
    
    @classmethod
    def create_job_script(cls,job):
        script= cls.job_script_path(job)  
        encoding = job.remote_host.config.run.encoding or 'UTF-8'
        with open(script, 'w',encoding=encoding,newline='\n') as f:
            f.write('#!/bin/bash\n\n')
            # Join stdout and stderr:
            f.write('#$ -j y\n')
            if job.setting['queingsystem']['queue'] != '':
                f.write('#$ -q {}\n'.format(job.setting['queingsystem']['queue']))
            if job.setting['queingsystem']['pe'] != '':
                f.write('#$ -pe {} {}\n'.format(job.setting['queingsystem']['pe'],job.setting['queingsystem']['cpu']))
            if job.setting['queingsystem']['ram'] != 0:
                f.write('#$ -l mem_total={}M\n'.format(job.setting['queingsystem']['ram']))
            if job.setting['queingsystem']['walltime'] != '0-0:0':
                walltime_string = job.setting['queingsystem']['walltime'].replace('-',':')
                days,hours,minutes = walltime_string.split(':')
                hours_including_days = str(int(days)*24 + int(hours))
                new_walltime_string = hours_including_days + ':' + minutes + ':00'
                #SGE format for walltime_string is hours:minutes:seconds
                f.write('#$ -l h_rt={}\n'.format(new_walltime_string))
            f.write('\nulimit -s unlimited\n')    
            f.write('\nINPUTDIR="$(pwd)"\n')
            
            
            f.write('if [ -z "$TMPDIR" ];then\n')
            f.write('TMPDIR="/tmp/${JOB_ID}_${JOB_NAME}"\n')
            f.write('mkdir -p "$TMPDIR"\n')
            f.write('fi\n\n')
            f.write('cp "$INPUTDIR/{}" "$TMPDIR"\n'.format(job.ins_name))
            f.write('cp "$INPUTDIR/{}" "$TMPDIR"\n'.format(job.hkl_name))
            f.write('cd "$TMPDIR"\n')
            
            f.write('echo "$(hostname):$(pwd)" > "$INPUTDIR/RUNDIR"\n')
            if job.setting['queingsystem']['wait_time'] != 0:
                f.write('\n')
                f.write('START_TIME="$(date +%s)"\n')
                f.write('\nwhile [ $(date +%s) -le $(($START_TIME + {} )) ];do\n'.format(cls.wait_time(job)))
                f.write('if [ -f "{}" -a -f "{}" ];then\n'.format(job.ins_name,job.hkl_name)) 

            #TODO
            #awk 'BEGIN{ORS=" " } {for(i=1;i<=NF;i++) print "\""$i"\"" }' RESTART
            
            f.write('{} {} {} -t{} > "$INPUTDIR/{}" 2>&1 \n'.format(job.setting['shelxlpath'],job.ins_hkl_name,' '.join(job.setting['shelxl_args']),job.setting['queingsystem']['cpu'],cls.output_filename()))
            
            
            if job.setting['queingsystem']['wait_time'] != 0:
                f.write('\nSTART_TIME="$(date +%s)"\n')
            
            f.write('mv * "$INPUTDIR"\n')
            f.write('touch ${INPUTDIR}/DONE \n')
        
            if job.setting['queingsystem']['wait_time'] != 0:
                f.write('\n')
                f.write('fi\n')
                f.write('sleep 2\n')
                f.write('done\n')
                
            f.write('rm -rf "$TMPDIR"\n\n')

            
            
    @classmethod
    def submit_job(cls,job):
        
        result = job.remote_host.run("cd '{}' && qsub '{}'".format(job.remote_workdir,job.job_script_path.name),hide=True)
        job_id = result.stdout.split()[2]
        try:
            #This test if the extracted string is really the job id (is integer). However, the job id is store as string
            job_id_int = int(job_id)
        except ValueError as exc:
            raise ValueError("The job id '{}' is not an integer".format(job_id)) from exc     
        return job_id 
    
    @staticmethod
    def job_status(job):
        result = job.remote_host.run('qstat',hide=True)
        id_position = None
        state_position = None
        for index,line in enumerate(result.stdout.splitlines()):
            if index == 0:
                for position,header in enumerate(line.split()):
                    if header == 'job-ID':
                        id_position = position
                    if header == 'state':
                        state_position = position
                continue
            
            if id_position == None:
                raise ValueError('Determining job status failed. Could not find job-ID')    
              
            fields = line.split()
            if fields[id_position] == job.job_id:
                if state_position is not None:
                    state = fields[state_position]
                    if state == 'q':
                        return 'queued'
                    return 'running'

                #Job is in qstat, but state is unknown. Assume job is running
                return 'running'
        #job is not in qstat
        return 'stopped'
    
    @classmethod
    def allows_resubmission(cls,job):
        return job.setting['queingsystem']['wait_time'] != 0
    

            
    @classmethod
    def get_compute_node(cls,job):   
        #return name of compute node as string
        result = job.remote_host.run('qstat',hide=True)
        queue_position = None
        id_position = None
        for index,line in enumerate(result.stdout.splitlines()):
            if index == 0:
                for position,header in enumerate(line.split()):
                    if header == 'job-ID':
                        id_position = position
                    if header == 'queue':
                        queue_position = position
                        
                continue
          
            if queue_position == None or id_position == None:
                #can not find queue or id column in qstat output
                return None  
              
            fields = line.split()
            if fields[id_position] == job.job_id:
                queue = fields[queue_position]
                compute_node = queue.split('@')[-1]
                return compute_node

        #job is not in qstat
        
        return None  
      
    @classmethod
    def kill_job(cls,job):
        job.remote_host.run('qdel {}'.format(job.job_id),hide=True)
    
    @classmethod
    def wait_time(cls,job):
        #return the wait time in seconds
        return job.setting['queingsystem']['wait_time'] * 60 
    
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
            'Name' : 'pe',
            'Label':'Parallel Environment',
            'Type' : 'LineEdit',
            'Default': 'smp'
        })
         
        settings.append({
            'Name' : 'ram',
            'Label':'RAM per core (MB)',
            'Type' : 'SpinBox',
            'Min' : '0',
            'Max' : '999999',
            'Default' : '2000',
        })
        settings.append({
            'Name' : 'walltime',
            'Label':'Walltime',
            'Type' : 'WalltimeWidget',
            'MaxDays' : '99',
        })   
        settings.append({
            'Name' : 'wait_time',
            'Label':'Keep resources reserved for (minutes)',
            'Type' : 'SpinBox',
            'Min' : '0',
            'Max' : '999999',
            'Default' : '0',
        })           
        return settings
  
  
    @classmethod
    def check_settings(cls,settings:dict):  
        error = super().check_settings(settings)
        if error is not None:
            return error
        if settings['shelxlpath'] == '':
            return 'Error: Path to ShelXL was not given'      
        if settings['queingsystem']['pe'] == '' and settings['queingsystem']['cpu'] > 1:
            return 'Error: When using more than 1 CPU, a parallel environment must be specified!'     
        return None
        
    
