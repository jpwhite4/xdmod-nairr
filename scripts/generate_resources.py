sql = """
SELECT
  RES.RESOURCE_ID,
  RES.RESOURCE_NAME,
  RES.DESCRIPTION,
  RTYPE.RESOURCE_TYPE,
  RES.PRODUCTION_BEGIN_DATE,
  RES.PRODUCTION_END_DATE,
  TRIM(
    COALESCE(O.organization_abbr, O.organization_name)
  ) AS "organization"
FROM
  "xras"."resources" AS RES
  JOIN "xras"."allocations_process_resources" AS APRES ON RES.RESOURCE_ID = APRES.RESOURCE_ID
  JOIN "xras"."allocations_processes" AS AP ON AP.ALLOCATIONS_PROCESS_ID = APRES.ALLOCATIONS_PROCESS_ID
  JOIN "xras"."organizations" as O ON O.organization_id = RES.organization_id
  LEFT JOIN "xras"."resource_types" AS RTYPE ON RTYPE.RESOURCE_TYPE_ID = RES.RESOURCE_TYPE_ID
WHERE
  AP.ALLOCATIONS_PROCESS_NAME = 'National Artificial Intelligence Research Resource'
  AND RES.PRODUCTION_BEGIN_DATE IS NOT NULL
ORDER BY
  RES.PRODUCTION_BEGIN_DATE ASC,
  RES.RESOURCE_NAME ASC
"""

import psycopg2
import json
import re
import configparser


rtype_map = {"Compute": "HPC", "Cloud": "Cloud", "Program": "Program"}


def demangle_name(inname):

    name = inname
    r = re.compile(r"^([^(]+)")
    mtch = r.match(name)
    if mtch:
        name = mtch.group(0)

    return re.sub(r"[^\w]", "-", name)


def main():

    XDMOD_CONFIG_PATH = "/data/www/xdmod/etc"

    config = configparser.ConfigParser()
    config.read(f"{XDMOD_CONFIG_PATH}/portal_settings.ini")

    resources = {}

    with open(f"{XDMOD_CONFIG_PATH}/resources.json", "r") as resources_file:
        for res in json.load(resources_file):
            resources[res["resource"]] = {"fact": res}

    with open(f"{XDMOD_CONFIG_PATH}/resource_specs.json", "r") as resourcespecs_file:
        for res in json.load(resourcespecs_file):
            resources[res["resource"]]["specs"] = res

    print(json.dumps(resources))

    with psycopg2.connect(
        database=config["tgcdbmirror"]["database"].strip("'"),
        host=config["tgcdbmirror"]["host"].strip("'"),
        user=config["tgcdbmirror"]["user"].strip("'"),
        password=config["tgcdbmirror"]["pass"].strip("'"),
        port=config["tgcdbmirror"]["port"].strip("'"),
    ) as conn:

        with conn.cursor() as curs:
            curs.execute(sql)
            for data in curs:

                resource = demangle_name(data[1])

                if resource not in resources:
                    resources[resource] = {
                        "fact": {
                            "resource": resource,
                            "resource_type": rtype_map[data[3]],
                            "name": data[1],
                            "description": data[2] or "",
                            "resource_allocation_type": "CPUNode",
                            "timezone": "EST",
                            "pi_column": "account_name",
                            "organization": data[6],
                        },
                        "specs": {
                            "resource": resource,
                            "start_date": data[4].strftime("%Y-%m-%d"),
                            "cpu_node_count": 1,
                            "cpu_processor_count": 1,
                            "cpu_ppn": 1,
                            "gpu_node_count": 0,
                            "gpu_processor_count": 0,
                            "gpu_ppn": 0,
                        },
                    }
                    if data[5]:
                        resources[resource]["specs"]["end_date"] = data[5].strftime(
                            "%Y-%m-%d"
                        )

        rfact = []
        rspec = []

        for info in resources.values():
            rfact.append(info["fact"])
            rspec.append(info["specs"])

        with open(f"{XDMOD_CONFIG_PATH}/resources.json", "w") as filep:
            json.dump(rfact, filep, indent=4)

        with open(f"{XDMOD_CONFIG_PATH}/resource_specs.json", "w") as filep:
            json.dump(rspec, filep, indent=4)


if __name__ == "__main__":
    main()
