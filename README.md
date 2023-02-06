# remoteXL
RemoteXL is an extension to the graphical user interface of shelXle. It allows the refinement of large crystal structures on a high-performance cluster directly from shelXle.   

## Work in Progress
- Supported queuing systems:
    - Slurm
    - Sun Grid Engine

Please don't hesitate to post bug reports or future requests.

## Installation 
1. Download the latest release and extract the zip file to a permanent folder (e.g. C:\remoteXL or C:\bn\remoteXL)
2. Copy the latest version of shelXL to your remote maschine (http://shelx.uni-goettingen.de/download.php)
3. In shelXle: Set remoteXL.exe as your shelXL executable.

## Usage:
1. Start the refinement in shelXle (F2)
2. Create a new connection to a remote host or select a local shelXL version: 
    e.g.
    
    ![integral](/remoteXL/pictures/NK.png)
    
3. Start the refinement with the selected settings.
