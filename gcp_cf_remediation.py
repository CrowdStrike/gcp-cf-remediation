from google.cloud import compute_v1
from google.oauth2 import service_account
from google.api_core.extended_operation import ExtendedOperation
import sys
import os
import glob
import random
import string
import csv
import logging

def get_logger(
        LOG_FORMAT     = '[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s',
        LOG_NAME       = __name__,
        LOG_FILE_INFO  = 'output.log',
        LOG_FILE_ERROR = 'error.log'):

    log           = logging.getLogger(LOG_NAME)
    log_formatter = logging.Formatter(LOG_FORMAT)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(log_formatter)
    log.addHandler(stream_handler)

    file_handler_info = logging.FileHandler(LOG_FILE_INFO)
    file_handler_info.setFormatter(log_formatter)
    file_handler_info.setLevel(logging.INFO)
    log.addHandler(file_handler_info)

    file_handler_error = logging.FileHandler(LOG_FILE_ERROR)
    file_handler_error.setFormatter(log_formatter)
    file_handler_error.setLevel(logging.ERROR)
    log.addHandler(file_handler_error)

    log.setLevel(logging.INFO)

    return log

def wait_for_extended_operation(
    operation: ExtendedOperation, verbose_name = "operation", timeout: int = 1800
):
    result = operation.result(timeout=timeout)

    if operation.error_code:
        print(
            f"Error during {verbose_name}: [Code: {operation.error_code}]: {operation.error_message}",
            file=sys.stderr,
            flush=True,
        )
        print(f"Operation ID: {operation.name}", file=sys.stderr, flush=True)
        raise operation.exception() or RuntimeError(operation.error_message)

    if operation.warnings:
        print(f"Warnings during {verbose_name}:\n", file=sys.stderr, flush=True)
        for warning in operation.warnings:
            print(f" - {warning.code}: {warning.message}", file=sys.stderr, flush=True)

    return result

class GcpFixBoot:
    def __init__(self, credentials, project, region):
        self.project = project
        self.region = region
        credentials = service_account.Credentials.from_service_account_file(credentials)
        self.instance_client = compute_v1.InstancesClient(credentials=credentials)
        self.disk_client = compute_v1.DisksClient(credentials=credentials)
        self.regio_disk_client = compute_v1.RegionDisksClient(credentials=credentials)
        self.snapshot_client = compute_v1.SnapshotsClient(credentials=credentials)
        self.image_client = compute_v1.ImagesClient(credentials=credentials)

    def get_disk(self,
        disk_name,
        zone = None,
        region = None,
        disk_project_id=None):

        try:
            if zone is None and region is None:
                raise RuntimeError(
                    "You need to specify `zone` or `region` for this function to work."
                )
            if zone is not None and region is not None:
                raise RuntimeError("You can't set both `zone` and `region` parameters.")

            if disk_project_id is None:
                disk_project_id = self.project

            if zone is not None:
                disk = self.disk_client.get(project=disk_project_id, zone=zone, disk=disk_name)
            else:
                disk = self.regio_disk_client.get(project=disk_project_id, region=region, disk=disk_name)
        except Exception as ex:
            logger.error(f"Failed to get disk {disk_name}: {str(ex)}")
            raise
        
        return disk

    def create_snapshot(self,
        disk_name,
        snapshot_name,
        zone = None,
        region = None,
        location = None,
        disk_project_id=None):

        logger.info(f"Attempting to create snapshot for {disk_name}")
        try:
            disk = self.get_disk(disk_name, zone, region, disk_project_id)

            snapshot = compute_v1.Snapshot()
            snapshot.architecture = disk.architecture
            snapshot.description = disk.description
            snapshot.labels = disk.labels

            snapshot.name = snapshot_name
            snapshot.source_disk = disk.self_link

            if location:
                snapshot.storage_locations = [location]

            operation = self.snapshot_client.insert(project=self.project, snapshot_resource=snapshot)
        except Exception as ex:
            logger.error(f"Failed to create snapshot for {disk_name}: {str(ex)}")
            raise

        return operation

    def create_disk_from_snapshot(self, disk_name, snapshot_link, zone, old_disk):
        logger.info(f"Attempting to create disk from snapshot {snapshot_link} for {disk_name}")
        try:
            disk = compute_v1.Disk()
            disk.architecture = old_disk.architecture
            if old_disk.async_primary_disk:
                disk.async_primary_disk = old_disk.async_primary_disk
            disk.description = old_disk.description
            disk.enable_confidential_compute = old_disk.enable_confidential_compute
            disk.guest_os_features = old_disk.guest_os_features
            disk.labels = old_disk.labels
            disk.license_codes = old_disk.license_codes
            disk.physical_block_size_bytes = old_disk.physical_block_size_bytes
            if old_disk.provisioned_iops:
                disk.provisioned_iops = old_disk.provisioned_iops
            if old_disk.provisioned_throughput:
                disk.provisioned_throughput = old_disk.provisioned_throughput
            disk.resource_policies = old_disk.resource_policies
            disk.size_gb = old_disk.size_gb
            disk.type_ = old_disk.type_
            if old_disk.replica_zones:
                disk.replica_zones = old_disk.replica_zones

            disk.name = disk_name
            disk.zone = zone
            disk.source_snapshot = snapshot_link
            operation = self.disk_client.insert(project=self.project, zone=zone, disk_resource=disk)

            wait_for_extended_operation(operation, "disk creation")
            logger.info(f"Created disk from snapshot {snapshot_link} for {disk_name}")

        except Exception as ex:
            logger.error(f"Failed to create disk from snapshot {snapshot_link} for {disk_name}: {str(ex)}")
            raise

        return self.disk_client.get(project=self.project, zone=zone, disk=disk_name)

    def attach_disk(self, zone, instance, new_disk, old_disk, index):
        disk_link = new_disk.self_link
        logger.info(f"Attempting to attach disk {disk_link} to {instance}")
        try:

            boot = False
            if index == 0:
                boot = True
            disk = compute_v1.AttachedDisk()
            disk.auto_delete = old_disk.auto_delete
            disk.device_name = old_disk.device_name
            disk.disk_size_gb = old_disk.disk_size_gb
            disk.guest_os_features = old_disk.guest_os_features
            disk.initialize_params = old_disk.initialize_params
            disk.interface = old_disk.interface
            disk.mode = old_disk.mode
            disk.type_ = old_disk.type_

            disk.boot = boot
            disk.index = index
            disk.source = disk_link

            operation = self.instance_client.attach_disk(request = {"project": self.project, "zone": zone, "instance": instance, "attached_disk_resource": disk})

            wait_for_extended_operation(operation, "attach disk")
            logger.info(f"Attached disk {disk_link} to {instance}")

        except Exception as ex:
            logger.error(f"Failed to attach disk {disk_link} to {instance}: {str(ex)}")
            raise

    def detach_disk(self, zone, instance, additional_disk):
        logger.info(f"Attempting to detach disk {additional_disk} from {instance}")
        try:
            operation = self.instance_client.detach_disk(request = {"project": self.project, "zone": zone, "instance": instance, "device_name": additional_disk})

            wait_for_extended_operation(operation, "detach disk")
            logger.info(f"Detached disk {additional_disk} from {instance}")

        except Exception as ex:
            logger.error(f"Failed to detach disk {additional_disk} from {instance}: {str(ex)}")
            raise

    def stop_instance(self, zone, instance_name):
        logger.info(f"Attempting to stop instance {instance_name}")
        try:
            operation = self.instance_client.stop(project=self.project, zone=zone, instance=instance_name)
            wait_for_extended_operation(operation, "instance stopping")
            logger.info(f"Stopped instance {instance_name}")
        except Exception as ex:
            logger.error(f"Failed to stop instance {instance_name}: {str(ex)}")
            raise

    def start_instance(self, zone, instance_name):
        logger.info(f"Attempting to start instance {instance_name}")
        try:
            operation = self.instance_client.start(project=self.project, zone=zone, instance=instance_name)
            wait_for_extended_operation(operation, "instance start")
            logger.info(f"Started instance {instance_name}")
        except Exception as ex:
            logger.error(f"Failed to start instance {instance_name}: {str(ex)}")
            raise

    def delete_file(self, disk_name, file_pattern):
        logger.info(f"Attempting to remove bad CrowdStrike file from {disk_name}")
        files = glob.glob(file_pattern)

        if not files:
            error_message = f"No matching CrowdStrike files found in {file_pattern}. Verify the right drive letter was specified."
            logger.error(error_message)
            raise OSError(error_message)

        for file_path in files:
            try:
                os.remove(file_path)
                logger.info(f"Successfully removed {file_path}")
            except OSError as e:
                logger.error(f"Failed to remove {file_path}: {e}")
                raise

    def assert_files_deleted(self, disk_name, file_pattern):
        logger.info(f"Checking for removal of bad files from {disk_name}")
        files = glob.glob(file_pattern)

        if files:
            error_message = f"Found files matching {file_pattern} after removal {str(files)}"
            logger.error(error_message)
            raise

        logger.info(f"No bad files found after deletion {disk_name}")

    def write_snapshots_file(self, instances, failed_snapshots, failed_fixes):
        snapshots = []
        for key, value in instances.items():
            snapshots.append(value.get("snapshot_name"))
        for key, value in failed_snapshots.items():
            snapshots.append(value.get("snapshot_name"))
        for key, value in failed_fixes.items():
            snapshots.append(value.get("snapshot_name"))
        with open("created_snapshots.log", 'a', encoding="UTF-8") as outfile:
            outfile.write('\n'.join(snapshots))
            outfile.write('\n')

    def write_original_disks_file(self, instances):
        original_disks = []
        for key, value in instances.items():
            original_disks.append(value.get("boot_disk_source"))
        with open("original_disks.log", 'a', encoding="UTF-8") as outfile:
            outfile.write('\n'.join(original_disks))
            outfile.write('\n')

def main(credentials, project, region, zone, recovery_instance_name, vms, leave_powered_off, drive_letter):
    file_pattern = f"{drive_letter}:/Windows/System32/drivers/CrowdStrike/C-00000291*.sys"
    gcp = GcpFixBoot(credentials, project, region)
    suffix = ''.join(random.choices(string.digits, k=5))
    logger.info(f"Beginning recovery attempt. Created resources will be created with the suffix:{suffix}")

    instances = {}
    failed_snapshots = {}
    failed_fixes = {}

    for instance_name in vms:
        instance = gcp.instance_client.get(project=project, zone=zone, instance=instance_name)
        gcp.stop_instance(zone, instance_name)

        boot_disk = next(disk for disk in instance.disks if disk.boot)
        disk_source = boot_disk.source.split("/")[-1]

        snapshot_name = f"{instance_name}-snapshot-{suffix}"
        operation = gcp.create_snapshot(disk_source, snapshot_name, zone)
        instances[instance_name] = {"instance": instance, "snapshot_operation": operation, "snapshot_name": snapshot_name, "boot_disk": boot_disk, "boot_disk_source": disk_source}
    
    try:
        # Snapshot operations are created above, and waited for all at once here to reduce time
        for instance_name, value in instances.items():
            try:
                wait_for_extended_operation(value["snapshot_operation"], "snapshot creation")
                logger.info(f"Created snapshot for {instance_name}")
                snapshot = gcp.snapshot_client.get(project=gcp.project, snapshot=value["snapshot_name"])
                value["snapshot"] = snapshot
            except Exception as ex:
                logger.error(f"Failed to create snapshot for {disk_source}: {str(ex)}")
                failed_snapshots[instance_name] = value
        for instance_name, value in failed_snapshots.items():
            del instances[instance_name]

        for instance_name, value in instances.items():
            try:
                old_disk = gcp.get_disk(value["boot_disk_source"], zone)
                new_disk_name = f"{value['boot_disk_source']}-rec-{suffix}"
                disk_self_link = value["snapshot"].self_link
                new_disk = gcp.create_disk_from_snapshot(new_disk_name, disk_self_link, zone, old_disk)
                value["new_disk"] = new_disk
                value["new_disk_name"] = new_disk_name
                device_name = value["boot_disk"].device_name

                # Fix Snapshots
                try:
                    gcp.attach_disk(zone, recovery_instance_name, value["new_disk"], value["boot_disk"], 1)
                    gcp.delete_file(value["new_disk_name"], file_pattern)
                    gcp.assert_files_deleted(value["new_disk_name"], file_pattern)
                finally:
                    try:
                        gcp.detach_disk(zone, recovery_instance_name, device_name)
                    except Exception as ex:
                        logger.error(f"Fatal error when detaching {device_name} from {recovery_instance_name}: {str(ex)}\nUnable to proceed.")
                        failed_fixes[instance_name] = value
                        break

                # Reattach disk to instance
                gcp.detach_disk(zone, instance_name, device_name)
                gcp.attach_disk(zone, instance_name, value["new_disk"], value["boot_disk"], 0)
                if not leave_powered_off:
                    gcp.start_instance(zone, instance_name)

            except Exception as ex:
                logger.error(f"Failed to fix instance {instance_name}: {str(ex)}")
                failed_fixes[instance_name] = value

        for instance_name, value in failed_fixes.items():
            del instances[instance_name]

    finally:
        gcp.write_snapshots_file(instances, failed_snapshots, failed_fixes)
        gcp.write_original_disks_file(instances)

        print("Attempted Recovery Complete.")
        print(f"Failures logged to error.log")
        print(f"Created snapshots logged to created_snapshots.log")
        print(f"Original disks from impacted machines logged to original_disks.log")
        print(f"Full output logged to output.log")

logger = get_logger()

if __name__=="__main__":
    import argparse

    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--credentials', required=True,
                            help='The path to the json file holding the GCP credentials.')
    parser.add_argument('--project', required=True, help='The GCP project to operate in')
    parser.add_argument('--region', required=True, help='The GCP region to operate in.')
    parser.add_argument('--zone', required=True, help='The GCP zone to operate in.')
    parser.add_argument('--instance_names', nargs="*", help='The names of the instances to recover separated by a space')
    parser.add_argument('--recovery_instance_name', required=True,
                        help='The name of the instance that will act as the recovery machine.')
    parser.add_argument('--instance_list_csv', help='The path to a csv file with a list of impact instaces')
    parser.add_argument('--leave_powered_off', action='store_true', help='''Leave the instances in a powered off state.
                        By default, instances will be powered on after the new disk is attached.''')
    parser.add_argument('--drive_letter', help='''The drive letter to search for problematic files on.
                        The default drive will be "D".''', choices=["D", "E", "F", "G"], default="D")
    parsed_args = parser.parse_args()

    instances_list = []
    if parsed_args.instance_list_csv:
        with open(parsed_args.instance_list_csv) as f:
            reader = csv.reader(f)
            for row in reader:
                instances_list += row
    if parsed_args.instance_names:
        instances_list += parsed_args.instance_names

    main(parsed_args.credentials, parsed_args.project, parsed_args.region, parsed_args.zone, parsed_args.recovery_instance_name, instances_list, parsed_args.leave_powered_off, parsed_args.drive_letter)
