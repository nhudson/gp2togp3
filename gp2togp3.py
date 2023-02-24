import argparse
import boto3
import botocore
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from tabulate import tabulate

######################################################################################
# Usage:
#    gp2togp3: This script can be used different ways, you can list all volumes in a
#              cluster and query the volume information in AWS.  If you use the 
#              --migrate flag it will print out a list of gp2 volumes to migrate to 
#              gp3.  
#
#    python ./gp2togp3 --region <AWS REGION> (default: us-east-1)
#                      --storage-class <kubernetes storage class filter>
#                      --volume-type <aws volume type filter> (eg: gp2/gp3/io1)
#                      --namespace <kubernetes namespace filter>
#                      --migrate (this is to migrate gp2 volumes to gp3)
#
#    eg: python ./gp2togp3 --region us-west-2 --storage-class default \
#                          --volume-type gp2 --migrate
######################################################################################

def get_pvc_info(corev1, claim_ref, claim_namespace):
    pvcs = corev1.read_namespaced_persistent_volume_claim(claim_ref, claim_namespace)
    return pvcs

def get_aws_volume_info(client, volume_id, type):
    if volume_id is None:
        return ('', '')

    # Extract the volume ID from the "aws:// format"
    if volume_id.startswith('aws://'):
        volume_id = volume_id.split('/')[-1]

    # Look up EBS volume in aws
    try:
        filters = [{'Name': 'volume-id', 'Values': [volume_id]}]
        if type is not None:
            filters.append({'Name': 'volume-type', 'Values': [type]})
        volume = client.describe_volumes(Filters=filters)

    except:
        # Return empty strings for volume type
        return (volume_id, '') 

    vols = volume['Volumes']
    if len(vols) == 0:
        return ('', '')

    # Get volume type and migration status
    volume_type = vols[0]['VolumeType']
            
    return (volume_id, volume_type)

def migrate_gp2_to_gp3(aws, volume_id):
    # Migrate the EBS volume from gp2 to gp3
    try:
        response = aws.modify_volume(VolumeId=volume_id, VolumeType='gp3')
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            print(f'Successfully migrated volume {volume_id} from gp2 to gp3')
            # Set a tag on the volume to reconcile the CSI driver
            aws.create_tags(Resources=[volume_id], Tags=[{'Key': 'ebs.csi.aws.com/reconcile', 'Value': 'true'}])
    except botocore.exceptions.ClientError as e:
        print(f'Error: {e}')

def main(storage_class, volume_type_filter, region, namespace, migrate):
    # Load the Kubernetes configuration
    config.load_kube_config()
    # Create a Kubernetes API client
    corev1 = client.CoreV1Api()
    # Create an AWS API client
    aws = boto3.client('ec2', region_name=region)
    # Define a list to hold the table data
    table_data = []

    # Get a list of all PVCs in the cluster
    pvc_list = []
    if namespace is None:
        pvc_list = corev1.list_persistent_volume_claim_for_all_namespaces(watch=False).items
    elif namespace is not None:
        pvc_list = corev1.list_namespaced_persistent_volume_claim(watch=False, namespace=namespace).items

    # Initialize list of volumes to be migrated
    volumes_to_migrate = []

    # Iterate over the PVCs and get volume data
    for pvc in pvc_list:
        # Check if the PVC is bound to a PV
        if pvc.spec.volume_name is None:
            continue

        try:
            # Get the PV information from the PVC
            pv = corev1.read_persistent_volume(pvc.spec.volume_name)

            # Get the AWS volume ID from the PV info
            if pv.spec.aws_elastic_block_store is not None:
                volume_id = pv.spec.aws_elastic_block_store.volume_id
            elif pv.spec.csi is not None:
                volume_id = pv.spec.csi.volume_handle
            else:
                volume_id = None

            # Get volume type (gp2/gp3/io1/io2) from AWS
            aws_volume_id, aws_vol_type = get_aws_volume_info(aws, volume_id, volume_type_filter)

            # Check if the storage class matches the filter, if one was provided
            if storage_class and pvc.spec.storage_class_name != storage_class:
                continue

            # Check if the volume type matches the filter, if one was provided
            if volume_type_filter and aws_vol_type != volume_type_filter:
                continue

            # Generate the output table
            table_data.append([
                pvc.metadata.name,
                aws_volume_id,
                pvc.metadata.namespace,
                pvc.spec.volume_name,
                pvc.spec.storage_class_name or 'None',
                aws_vol_type,
            ])

            # If the migrate flag is set and the volume type is gp2, add it to the list of volumes to migrate
            if migrate and aws_vol_type == 'gp2':
                volumes_to_migrate.append(aws_volume_id)

        except ApiException as e:
            if e.status == 404:
                print('Error: Resource not found.')
            else:
                print(f'Error: {e.reason}')

    # If we're migrating, print a list of volumes to be migrated and prompt for confirmation
    if migrate and volumes_to_migrate:
        print('The following volumes will be migrated from gp2 to gp3:')
        for volume_id in volumes_to_migrate:
            print(f'  {volume_id}')
        response = input('Do you want to proceed with the migration? (YES/NO) ')
        if response.upper() != 'YES':
            print('Migration cancelled.')
            return

    # Migrate volumes from gp2 to gp3, if requested
    if migrate and volumes_to_migrate:
        print('Migrating volumes...')
        for volume_id in volumes_to_migrate:
            try:
                migrate_gp2_to_gp3(aws, volume_id)
            except botocore.exceptions.ClientError as e:
                print(f'Error: {e}')

    # Print the table
    headers = ['PVC Name', 'Volume ID', 'Namespace', 'PV Name', 'Storage Class', 'Volume Type']
    print(tabulate(table_data, headers=headers))

if __name__ == '__main__':
    # Parse command-line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-class', type=str, default=None, help='Filter by storage class name')
    parser.add_argument('--volume-type', type=str, default=None, help='Filter by volume type (e.g. gp2, gp3, io1)')
    parser.add_argument('--region', type=str, default='us-east-1', help='AWS region to query')
    parser.add_argument('--namespace', type=str, default=None, help='Kubernetes namespace to filter on')
    parser.add_argument('--migrate', action='store_true', default=False, help='Migrate volumes from gp2 to gp3')
    args = parser.parse_args()

    # If the migrate flag is set, make sure volume-type and storage-class filters are also set
    if args.migrate and (args.volume_type is None or args.storage_class is None):
        print('Error: You must set both the volume-type and storage-class filters to migrate volumes')
        exit(1)

    # Run the script
    main(storage_class=args.storage_class, volume_type_filter=args.volume_type, region=args.region, namespace=args.namespace, migrate=args.migrate)
