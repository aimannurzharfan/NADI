"""Read-only Huawei Cloud check for huawei mode: can our keys see the services NADI needs?

Lists (never creates or changes) IoTDA devices, SMN topics, ECS servers, RDS and DCS instances.
Refuses to run unless NADI_MODE=huawei and HUAWEICLOUD_AK/SK are set, so it can't call the cloud by accident.
Run it once the competition coupon is active, before switching the server to huawei mode.

    python deploy/huawei_preflight.py
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def clients(ak, sk, region):
    from huaweicloudsdkcore.auth.credentials import BasicCredentials, DerivedCredentials
    from huaweicloudsdkdcs.v2 import DcsClient
    from huaweicloudsdkdcs.v2.region.dcs_region import DcsRegion
    from huaweicloudsdkecs.v2 import EcsClient
    from huaweicloudsdkecs.v2.region.ecs_region import EcsRegion
    from huaweicloudsdkiotda.v5 import IoTDAClient
    from huaweicloudsdkiotda.v5.region.iotda_region import IoTDARegion
    from huaweicloudsdkrds.v3 import RdsClient
    from huaweicloudsdkrds.v3.region.rds_region import RdsRegion
    from huaweicloudsdksmn.v2 import SmnClient
    from huaweicloudsdksmn.v2.region.smn_region import SmnRegion

    cred = BasicCredentials(ak, sk)
    # IoTDA standard edition: app-side endpoint from Console > IoTDA > Overview > Access Details
    iotda = IoTDAClient.new_builder().with_credentials(
        BasicCredentials(ak, sk).with_derived_predicate(DerivedCredentials.get_default_derived_predicate()))
    endpoint = os.getenv("IOTDA_API_ENDPOINT")
    iotda = iotda.with_endpoints([endpoint]) if endpoint else iotda.with_region(IoTDARegion.value_of(region))
    return {
        "IoTDA": iotda.build(),
        "SMN": SmnClient.new_builder().with_credentials(cred).with_region(SmnRegion.value_of(region)).build(),
        "ECS": EcsClient.new_builder().with_credentials(cred).with_region(EcsRegion.value_of(region)).build(),
        "RDS": RdsClient.new_builder().with_credentials(cred).with_region(RdsRegion.value_of(region)).build(),
        "DCS": DcsClient.new_builder().with_credentials(cred).with_region(DcsRegion.value_of(region)).build(),
    }


def main():
    if os.getenv("NADI_MODE", "local").strip().lower() != "huawei":
        sys.exit("NADI_MODE is not huawei: refusing to call Huawei Cloud.")
    ak, sk = os.getenv("HUAWEICLOUD_AK"), os.getenv("HUAWEICLOUD_SK")
    if not (ak and sk):
        sys.exit("HUAWEICLOUD_AK / HUAWEICLOUD_SK not set in .env.")
    region = os.getenv("HUAWEICLOUD_REGION", "ap-southeast-1")

    from huaweicloudsdkdcs.v2 import ListInstancesRequest as DcsList
    from huaweicloudsdkecs.v2 import ListServersDetailsRequest
    from huaweicloudsdkiotda.v5 import ListDevicesRequest
    from huaweicloudsdkrds.v3 import ListInstancesRequest as RdsList
    from huaweicloudsdksmn.v2 import ListTopicsRequest

    c = clients(ak, sk, region)
    checks = [
        ("IoTDA", lambda: [d.device_id for d in c["IoTDA"].list_devices(ListDevicesRequest(limit=10)).devices or []]),
        ("SMN", lambda: [t.name for t in c["SMN"].list_topics(ListTopicsRequest(limit=10)).topics or []]),
        ("ECS", lambda: [s.name for s in c["ECS"].list_servers_details(ListServersDetailsRequest(limit=10)).servers or []]),
        ("RDS", lambda: [i.name for i in c["RDS"].list_instances(RdsList(limit=10)).instances or []]),
        ("DCS", lambda: [i.name for i in c["DCS"].list_instances(DcsList(limit=10)).instances or []]),
    ]
    failed = 0
    for name, fn in checks:
        try:
            print(f"OK   {name:<5} {fn()}")
        except Exception as e:
            failed += 1
            print(f"FAIL {name:<5} {type(e).__name__}: {str(e)[:200]}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
