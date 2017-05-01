######
#
# AWS auto snapshot script - 2017-04-30
# Forked from https://github.com/viyh/aws-scripts
#
# Snapshot all EC2 volumes and delete snapshots older than retention time
#
# Required IAM permissions:
#   ec2:DescribeInstances
#   ec2:DescribeVolumes
#   ec2:CreateSnapshot
#   ec2:DeleteSnapshot
#   ec2:DescribeSnapshots
#   ec2:CreateTags
#
# Also need to setup the AWS region and credential files:
#   ~/.aws/credentials
#   ~/.aws/config
#
# More: https://boto3.readthedocs.io/en/latest/guide/quickstart.html#configuration
#

import boto3
import subprocess as sp
import syslog
from datetime import tzinfo, timedelta, datetime

syslog.openlog("autosnap")

# number of days to retain snapshots for
retention_days = 7

# create snapshot for volume
def create_volume_snapshot(instance_name, volume):
    description = "autosnap_{}.{}_{}".format(instance_name, volume.volume_id, datetime.now().strftime("%Y%m%d_%H%M%S"))
    snapshot = volume.create_snapshot(Description=description)
    if snapshot:
        snapshot.create_tags(Tags=[{'Key': 'Name', 'Value': description}])
        syslog.syslog("Created snapshot {} for {}.{}.".format(snapshot.id, instance_name, volume.volume_id))


# find and delete snapshots older than retention_days
def prune_volume_snapshots(retention_days, volume):
    for s in volume.snapshots.all():
        snapshot_id, snapshot_start_time = s.id, s.start_time
        now = datetime.now(s.start_time.tzinfo)
        is_old_snapshot = (now - s.start_time) > timedelta(days=retention_days)
        if is_old_snapshot and s.description.startswith('autosnap_'): 
            s.delete()
            syslog.syslog("Deleted snapshot {} created at {}.".format(snapshot_id, str(snapshot_start_time)))


def snapshot_volumes(instance_name, retention_days, volumes):
    for v in volumes:
        create_volume_snapshot(instance_name, v)
        prune_volume_snapshots(retention_days, v)


def get_current_instance(ec2):
    instance_id = sp.check_output(["curl", "-s", "http://169.254.169.254/latest/meta-data/instance-id"]).decode("utf-8")
    instances = list(ec2.instances.filter(Filters=[{"Name": "instance-id", "Values": [instance_id]}]))
    if not instances:
        raise Exception("Instance not found for ID: {}.".format(instance_id))
    else:
        return instances

#####
#####
#####

syslog.syslog("AWS auto snapshot script started.")
try:
    ec2 = boto3.resource('ec2')
    instances = get_current_instance(ec2)
    for i in instances:
        tags = {tag["Key"]: tag["Value"] for tag in i.tags}
        instance_name = tags.get("Name", i.id)
        volumes = ec2.volumes.filter(Filters=[{'Name': 'attachment.instance-id', 'Values': [i.id]}])
        snapshot_volumes(instance_name, retention_days, volumes)
    syslog.syslog("AWS auto snapshot script completed.")
except Exception as e:
    syslog.syslog(syslog.LOG_ERR, str(e))
