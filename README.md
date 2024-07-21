# GCP CrowdStrike File Remediation Script

A Python script designed to remediate CrowdStrike files causing a blue screen of death (BSOD) on Windows machines in Google Cloud Platform (GCP).

## Overview

This script is intended to run on a recovery machine in GCP to remediate files related to CrowdStrike that are causing a blue screen of death (BSOD) on Windows machines. The script performs the following steps on a list of provided instances:

1. Take a snapshot of the boot disk.
2. Create a disk from that snapshot.
3. Attach the new disk to the recovery machine as a secondary disk.
4. Delete the problematic files.
5. Detach the new disk from the recovery machine.
6. Shut down the impacted instance.
7. Detach the original disk from the impacted instance.
8. Attach the modified disk to the impacted instance.
9. Optionally power the impacted instance on.

This process allows the sensor to initialize without loading the problematic files.

## Disclaimers

- This script will not work with customer-managed encryption keys (CMEK).
- Snapshots and disks are not deleted in this process. They should be cleaned up after recovery has been verified.
- The name of the attached disk will change during the process, which may impact any external automation that looks at resource names, such as Terraform.

## Prerequisites

- Provision a GCP instance to act as the recovery machine.
  - This machine must be in the same region and zone as the impacted instances.
- Copy your GCP JSON credentials file to the recovery machine.
- Install Python on the recovery machine.

## GCP Credentials

1. Go to the IAM & Admin page.
2. Create a service account with the following roles:
   - ***Compute Admin***
   - ***Service Account User***
3. Click on Manage Keys.
   - Create a new JSON key.
4. Save this file locally in case you need it again.
5. Copy it to the recovery machine.

## Recovery Machine

> [!WARNING]
> A recovery machine must be created in the project, region, and zone that impacted instances are in.

The following are the requirements for the recovery machine:

- Must be a Windows machine.
  - We tested with `windows-server-2019-dc-v20240711`, but any current Windows instance should work.
- This instance must have a **single drive** attached.
- Must be able to download/install files from the internet.

## Example Python Installation

Run the follwing in PowerShell as administrator:

```PowerShell
$file = "https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe"
Invoke-WebRequest -Uri $file -OutFile python-3.12.4-amd64.exe
./python-3.12.4-amd64.exe /quiet InstallAllUsers=0 InstallLauncherAllUsers=0 PrependPath=1 Include_test=0
```

Close PowerShell and reopen it as administrator:

```PowerShell
python -m venv env
.\env\Scripts\Activate.ps1
pip install -U google-auth google-cloud-compute
```

## Running the remediation

### Download the script

To download the script, run the following in PowerShell:

```PowerShell
$file = "https://raw.githubusercontent.com/CrowdStrike/gcp-cf-remediation/main/gcp_cf_remediation.py"
Invoke-WebRequest -Uri $file -OutFile gcp_cf_remediation.py
```

### Running the script with a list of impacted instances

Impacted instances can be provided as a list from the command line

```PowerShell
$GCP_CREDENTIALS = "Path to your credential file"
$PROJECT = "Your Project"
$REGION = "Your Region"
$ZONE = "Your Zone"
$RECOVERY_INSTANCE = "Your Recovery Instance"
python gcp_cf_remediation.py --credentials $GCP_CREDENTIALS --project $PROJECT --region $REGION --zone $ZONE --recovery_instance_name $RECOVERY_INSTANCE --instance_name impacted-instance-1 impacted-instance-2
```

### Running the script with a list of impacted instances from a CSV file

Alternatively a CSV file can also be used for the list of instances to run recovery on

> Example CSV file (`SomeFile.csv`):
>
> ```csv
> impacted-instance-1,impacted-instance-2
> ```

```PowerShell
python gcp_cf_remediation.py  --credentials $GCP_CREDENTIALS --project $PROJECT --region $REGION --zone $ZONE --recovery_instance_name $RECOVERY_INSTANCE --instance_list_csv "SomeFile.csv"
```

### Managing state of the instances after recovery

By default the instances will be powered on after they are recovered, if you do not want them to be powered on, use the `--leave_powered_off` flag

> [!NOTE]
> This flag will effect **all** instances being passed in.
>
> If you want to manage the state differently for different instances, it is recommended to separate the list of instances by state. This way you can run the script with the appropriate flags for each list.

```PowerShell
python gcp_cf_remediation.py  --credentials $GCP_CREDENTIALS --project $PROJECT --region $REGION --zone $ZONE --recovery_instance_name $RECOVERY_INSTANCE --instance_list_csv "SomeFile.csv" --leave_powered_off
```

### Output

The `gcp_cf_remediation.py` script will log to stdout and will also append logs to the following log files:

- **output.log**: Contains all messages that get logged to stdout during the remediation attempt.
- **error.log**: Contains all error events that happened during the remediation attempt.
- **created_snapshots.log**: Contains a list of snapshots that were created during the remediation attempt.
  - These can be deleted after remediation has been verified.
- **original_disks.log**: Contains a list of disks from the impacted instances fixed by the remediation attempt.
  - These can be deleted after remediation has been verified and it's been confirmed that they are no longer needed.

## Statement of Support

This project is a community-driven, opens source project designed to remediate CrowdStrike files causing a blue screen of death (BSOD) on Windows machines in Google Cloud Platform (GCP). While not a formal CrowdStrike product, it is maintained by CrowdStrike and supported in partnership with the open source community.

For additional details, see the [SUPPORT](SUPPORT.md) file.

## License

See the [LICENSE](LICENSE) file for details.
