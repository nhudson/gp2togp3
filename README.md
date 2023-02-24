# gp2togp3

This is a python script to gather volume information from a Kubernetes cluster
running in AWS.  The information can then be used to migrate volumes types from
gp2 to gp3 if you want.

## Running

Running the script is pretty easy.  You need to have your Kubernetes Context set
and have the approporiate IAM access in AWS.

```
python ./gp2togp3.py
```

The script assumes AWS Region `us-east-1` by default.  The above command will return
a table of every volume bound in a Kubernetes cluster like so.

```
PVC Name                    Volume ID              Namespace        PV Name                                   Storage Class    Volume Type
--------------------------  ---------------------  ---------------  ----------------------------------------  ---------------  -------------
data-an-0                   vol-0d78b72f9964506a6  aaaaaaaaaa       pvc-219ec545-27b1-4dee-a3e5-852d132139d0  ebs              gp3
data-an-1                   vol-04c44db2199947fc9  aaaaaaaaaa       pvc-2c5228c3-9cee-47a9-92c9-1f638451193f  ebs              gp3
data-an-2                   vol-06c51abfc6eb367f0  aaaaaaaaaa       pvc-e202bf71-8fd8-4447-8343-55990863ad30  ebs              gp3
data-an-0                   vol-0f158c6555f293fb0  bbbbbbbbbb       pvc-c658ef23-3029-4895-8a16-290164e38348  ssd              gp2
data-an-1                   vol-0570024bea201d8a8  bbbbbbbbbb       pvc-2738e59b-35ae-40e7-b7fe-b3a02266d8e7  ssd              gp2
data-an-2                   vol-08bac1d23bbdb6491  bbbbbbbbbb       pvc-29b1fdc6-15d4-4107-b9e5-2b42709f03af  ssd              gp2
```

## Flags

| **flag** | **default** | **usage** | 
|:----:|:----:|:----:|
| `--region` | `us-east-1` | AWS Region |
| `--storage-class` | All | Filter by a specific Kubernetes storage class |
| `--volume-type` | All | Filter by a specific AWS Volume Type (gp2/gp3/io1/io2) |
| `--namespace` | All | Filter by a Kubernetes namespace |
| `--migrate` | False | Generate a list of gp2 volumes by volume-type and storage-class to be migrated from gp2 to gp3.  If set `--volume-type` & `--storage-class` will be required |
