# gcp-cf-remediaton

A python script that will attempt to remediate CrowdStrike files causing a blue screen of death on windows machines.

## Overview

This script is intended to run on a recovery machine in GCP.
It will loop through a list of provided instances to do the following:
* Take a snapshot of the boot disk
* Create a disk from that snapshot
* Attach the new disk to the recovery machine as a secondary disk
* Delete the bad files
* Detach the new disk from the recovery machine
* Shut down the impacted instance
* Detach the original disk from the the impacted instance
* Attach the modified disk to the impacted instance
* Optionally power the impacted instance on

This will allow sensor to initialize without loading the bad files.

## Disclaimers

* This will not work with customer managed encryption keys (CMEK).
* Snapshots and disks are not deleted in this process. They should be cleaned up at a later point after recovery has been verified.
* The name of the attached disk will change during the process, so any external automation that looks at resource names, such at terraform, may be impacted.

## Prerequisites

* Provision a GCP instance to act as the recovery machine.
  * This machine must be in the same region and zone as the impacted instances
* Copy your GCP json credentials file to the recovery machine
* Install python on the recovery machine

## GCP Credentials

* GO to the IAM & Admin page
* Create a service account with the following roles
  * Compute Admin
  * Serice Account User
* Click on Manage Keys
  * Create New Json Key
* Save this file locally in case you need it again
* Copy it to the recovery machine

## Recovery Machine

* A recovery machine must be created in the project, region, and zone that impacted instances are in.
  * `windows-server-2019-dc-v20240711` was used for testing, but any current windows instance should work

## Example Python Installation

Run the follwing in PowerShell as administrator
```PowerShell
$file = "https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe"
Invoke-WebRequest -Uri $file -OutFile python-3.12.4-amd64.exe
./python-3.12.4-amd64.exe /quiet InstallAllUsers=0 InstallLauncherAllUsers=0 PrependPath=1 Include_test=0
```

Close PowerShell and reopen it as administrator
```PowerShell
python -m venv env
.\env\Scripts\Activate.ps1
pip install -U google-auth google-cloud-compute
```

## Running the remediation

```PowerShell
$GCP_CREDENTIALS = "Path to your credential file"
$PROJECT = "Your Project"
$REGION = "Your Region"
$ZONE = "Your Zone"
$RECOVERY_INSTANCE = "Your Recovery Instance"
python gcp_cf_remediation.py --credentials $GCP_CREDENTIALS --project $PROJECT --region $REGION --zone $ZONE --recovery_instance_name $RECOVERY_INSTANCE --instance_name impacted-instance-1 impacted-instance-2
```

A CSV file can also be used for the list of instance to run recover

```PowerShell
python gcp_cf_remediation.py  --credentials $GCP_CREDENTIALS --project $PROJECT --region $REGION --zone $ZONE --recovery_instance_name $RECOVERY_INSTANCE --instance_list_csv "SomeCsvFile"
```

By default the instances will be powered on after they are recovered, if you do not want them to be powered on, use the --leave_powered_off flag

```PowerShell
python gcp_cf_remediation.py  --credentials $GCP_CREDENTIALS --project $PROJECT --region $REGION --zone $ZONE --recovery_instance_name $RECOVERY_INSTANCE --instance_list_csv "SomeCsvFile" --leave_powered_off
```

### Output

gcp_cf_remediation.py will log to stdout, and will also append logs to the following log files
* output.log
  * This contains all messages that get logged to stdout during the remediation attempt
* error.log
  * This contains all error events that happened during the remediation attempt
* created_snapshots.log
  * This contains a list of snapshots that were created during the remediation attempt
    * These can be deleted after remediation has been verified
* original_disks.log
  * This contains a list of disks from the impacted instances fixed by the remediation attempt
    * These can be deleted after remediation has been verified, and it's been confirmed that they are no longer needed.
