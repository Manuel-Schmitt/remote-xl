from remoteXL.backend.queingsystems.base_queingsystem import BaseQuingsystem

class Slurm(BaseQuingsystem):
    _displayname = 'Slurm'
    @classmethod
    def job_script_path(cls,job):
        return job.ins_hkl_path.with_suffix('.sbatch')
    
    @classmethod
    def create_job_script(cls,job):
        script= cls.job_script_path(job)  
        encoding = job.remote_host.config.run.encoding or 'UTF-8'
        with open(script, 'w',encoding=encoding,newline='\n') as f:
            f.write('#!/bin/bash\n\n')
            f.write('##############################################\n')    
            f.write('#SBATCH --job-name {}\n'.format(job.ins_hkl_name))     
            f.write('#SBATCH --ntasks={} --nodes=1\n'.format(job.setting['queingsystem']['cpu']))
            if job.setting['queingsystem']['ram'] != 0:
                f.write('#SBATCH --mem-per-cpu={}M\n'.format(job.setting['queingsystem']['ram']))
            if job.setting['queingsystem']['disk'] != 0:
                f.write('#SBATCH  --gres=scratch:{}G\n'.format(job.setting['queingsystem']['disk']))
            if job.setting['queingsystem']['walltime'] != '0-0:0':
                f.write('#SBATCH --time {}\n'.format(job.setting['queingsystem']['walltime']))
            f.write('##############################################\n')  
            f.write('\nulimit -s unlimited\n')
            f.write('\nINPUTDIR="${SLURM_SUBMIT_DIR:=$(pwd)}"\n')
            f.write('TMP_WORK_DIR="${SCRATCH:=${TMPDIR:=/tmp/${USER}_${SLURM_JOB_NAME}}}"\n\n')
            f.write('test ! -d "${TMP_WORK_DIR}" && mkdir -p "${TMP_WORK_DIR}"\n')
            f.write('cd "${TMP_WORK_DIR}"\n')
            f.write('echo "$(hostname):$(pwd)" > "${INPUTDIR}/RUNDIR"\n')
            
            f.write('cp "$INPUTDIR/{}" "$TMP_WORK_DIR"\n'.format(job.ins_name))
            f.write('cp "$INPUTDIR/{}" "$TMP_WORK_DIR"\n'.format(job.hkl_name))
            
            if job.setting['queingsystem']['wait_time'] != 0:
                f.write('\n')
                f.write('START_TIME="$(date +%s)"\n')
                f.write('\nwhile [ $(date +%s) -le $(($START_TIME + {} )) ];do\n'.format(cls.wait_time(job)))
                f.write('if [ -f "{}" -a -f "{}" ];then\n'.format(job.ins_name,job.hkl_name))            
            
            
            f.write('\n{} {} {} -t{} > "$INPUTDIR/{}" 2>&1 \n'.format(job.setting['shelxlpath'],job.ins_hkl_name,' '.join(job.setting['shelxl_args']),job.setting['queingsystem']['cpu'],cls.output_filename()))
            
            
            if job.setting['queingsystem']['wait_time'] != 0:
                f.write('\nSTART_TIME="$(date +%s)"\n')
            
            f.write('mv * "$INPUTDIR"\n')
            f.write('touch ${INPUTDIR}/DONE \n')
        
            if job.setting['queingsystem']['wait_time'] != 0:
                f.write('\n')
                f.write('fi\n')
                f.write('sleep 2\n')
                f.write('done\n')
            
            f.write('sleep 2\n')
            f.write('rm -rf "$TMPDIR"\n')
            
            
    @classmethod
    def submit_job(cls,job):
        
        result = job.remote_host.run("cd '{}' && sbatch '{}'".format(job.remote_workdir,job.job_script_path.name),hide=True)
        job_id = result.stdout.split()[3]
        try:
            #This test if the extracted string is really the job id (is integer). However, the job id is store as string
            id_int = int(job_id)
        except ValueError as exc:
            raise ValueError("The job id '{}' is not an integer".format(job_id)) from exc
        return job_id 
    
    @staticmethod
    def job_status(job):
        result = job.remote_host.run('squeue',hide=True)
        id_position = None
        state_position = None
        for index,line in enumerate(result.stdout.splitlines()):
            if index == 0:
                for position,header in enumerate(line.split()):
                    if header == 'JOBID':
                        id_position = position
                    if header == 'ST':
                        state_position = position
                continue
            
            if id_position == None:
                raise ValueError('Determining job status failed. Could not find job-ID')    
              
            fields = line.split()
            if fields[id_position] == job.job_id:
                if state_position is not None:
                    state = fields[state_position]
                    if state == 'PD':
                        return 'queued'
                    if state == 'DL':
                        return 'stopped'
                    if state == 'R':
                        return 'running'
                    if state == 'ST':
                        return 'stopped'
                    if state == 'TO':
                        return 'stopped'
                    #Dont know job state. Assume job is running
                    return 'running'
                #Job is in squeue output, but state is unknown. Assume job is running
                return 'running'
        #job is not in squeue output
        return 'stopped'
    
    @classmethod
    def allows_resubmission(cls,job):
        return job.setting['queingsystem']['wait_time'] != 0
    
    @classmethod
    def get_compute_node(cls,job):
        #return name of compute node as string
        result = job.remote_host.run('qstat',hide=True)
        node_position = None
        id_position = None
        for index,line in enumerate(result.stdout.splitlines()):
            if index == 0:
                for position,header in enumerate(line.split()):
                    if header == 'JOBID':
                        id_position = position
                    if header == 'NODELIST(REASON)':
                        node_position = position
                        
                continue
          
            if node_position == None or id_position == None:
                #can not find queue or id column in qstat output
                return None  
              
            fields = line.split()
            if fields[id_position] == job.job_id:
                compute_node = fields[node_position]
                if compute_node[0] == '(':
                    #Job is not running and this column contains the reason.
                    return None
                return compute_node
        
        #job is not in qstat
        return None
    
    @classmethod
    def kill_job(cls,job):
        job.remote_host.run('scancel {}'.format(job.job_id),hide=True)
    
    @classmethod
    def wait_time(cls,job):
        #return the wait time in seconds
        return job.setting['queingsystem']['wait_time'] * 60 
    
    @staticmethod
    def needed_settings():
        settings = []   
        settings.append({
            'Name' : 'cpu',
            'Label':'CPU',
            'Type' : 'SpinBox',
            'Min' : '1',
            'Max' : '99',
            'Default' : '1',
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
            'Name' : 'disk',
            'Label':'Disk storage per core (GB)',
            'Type' : 'SpinBox',
            'Min' : '0',
            'Max' : '999999',
            'Default' : '0',
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
        return None

